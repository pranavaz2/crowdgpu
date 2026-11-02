/**
 * SubmitJobPage — /jobs/submit route
 *
 * GPU workload submission form.
 *
 * Currently submits via mock createJob() in jobsService.
 * When POST /api/v1/jobs is implemented, update jobsService.js only —
 * this page's field structure remains unchanged.
 *
 * Fields map to the frontend job model defined in jobsService.js.
 * The backend schema may differ — adopt exact fields after the coordinator
 * job API specification is finalised.
 */

import { useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import PageLayout from '../components/layout/PageLayout.jsx';
import { createJob } from '../services/jobsService.js';

// ── Workload presets ────────────────────────────────────────────────────────
const WORKLOAD_PRESETS = [
  {
    type: 'matrix_multiply',
    name: 'Matrix Multiplication (CUDA)',
    description: 'Runs PyTorch matrix multiplication on GPU with configurable dimension.',
    defaultCommand: 'matrix_multiply',
    defaultVram: 512,
    defaultJobName: 'CUDA Matrix Multiplication',
  },
  {
    type: 'vector_add',
    name: 'Vector Addition (CUDA)',
    description: 'Runs element-wise addition of 10M float32 vectors on GPU.',
    defaultCommand: 'vector_add',
    defaultVram: 256,
    defaultJobName: 'CUDA Vector Addition',
  },
  {
    type: 'benchmark',
    name: 'MatMul Benchmark (CUDA)',
    description: 'Executes timed synchronized GPU MATMUL loops and computes GFLOPS.',
    defaultCommand: 'benchmark',
    defaultVram: 1024,
    defaultJobName: 'CUDA MatMul Benchmark',
  },
  {
    type: 'docker',
    name: 'Custom Docker Container',
    description: 'Runs a container image in an isolated GPU sandbox environment.',
    defaultCommand: 'python train.py --epochs 10',
    defaultVram: 2048,
    defaultJobName: 'Custom Container Job',
  },
];

// ── VRAM options ─────────────────────────────────────────────────────────────
const VRAM_OPTIONS = [
  { label: '256 MiB — Safe Minimal', value: 256 },
  { label: '512 MiB — Lightweight',    value: 512 },
  { label: '1 GB  — 1,024 MiB',        value: 1024 },
  { label: '2 GB  — 2,048 MiB',        value: 2048 },
  { label: '4 GB  — 4,096 MiB',        value: 4096 },
  { label: '8 GB  — 8,192 MiB',        value: 8192 },
  { label: '12 GB — 12,288 MiB',       value: 12288 },
  { label: '16 GB — 16,384 MiB',       value: 16384 },
  { label: '24 GB — 24,576 MiB',       value: 24576 },
];

const INITIAL_FORM = {
  name:             'CUDA Matrix Multiplication',
  workload_type:    'matrix_multiply',
  docker_image:     '',
  command:          'matrix_multiply',
  vram_required_mb: 512,
};

// ── Validation rules ─────────────────────────────────────────────────────────
function validate(form) {
  const errors = {};

  if (!form.name.trim()) {
    errors.name = 'Job name is required.';
  } else if (form.name.trim().length > 120) {
    errors.name = 'Job name must be 120 characters or fewer.';
  }

  if (form.workload_type === 'docker') {
    if (!form.docker_image.trim()) {
      errors.docker_image = 'Docker image is required for container workloads.';
    } else if (!/^[a-zA-Z0-9][a-zA-Z0-9._/:@-]*$/.test(form.docker_image.trim())) {
      errors.docker_image = 'Enter a valid Docker image reference (e.g. pytorch/pytorch:latest).';
    }
  }

  if (!form.command.trim()) {
    errors.command = 'Command or workload operation is required.';
  }

  const vram = Number(form.vram_required_mb);
  if (!vram || vram <= 0) {
    errors.vram_required_mb = 'Select a valid VRAM requirement.';
  }

  return errors;
}

export default function SubmitJobPage() {
  const navigate = useNavigate();

  const [form,        setForm]        = useState(INITIAL_FORM);
  const [touched,     setTouched]     = useState({});
  const [submitting,  setSubmitting]  = useState(false);
  const [submitError, setSubmitError] = useState(null);
  const [submitted,   setSubmitted]   = useState(false);

  const errors = validate(form);
  const hasErrors = Object.keys(errors).length > 0;

  function handleBlur(e) {
    setTouched((prev) => ({ ...prev, [e.target.name]: true }));
  }

  function handleChange(e) {
    const { name, value } = e.target;
    setForm((prev) => ({ ...prev, [name]: value }));
  }

  function handleWorkloadTypeChange(type) {
    const preset = WORKLOAD_PRESETS.find((p) => p.type === type);
    if (!preset) return;

    setForm((prev) => ({
      ...prev,
      workload_type:    type,
      name:             preset.defaultJobName,
      command:          preset.defaultCommand,
      vram_required_mb: preset.defaultVram,
      docker_image:     type === 'docker' ? 'pytorch/pytorch:latest' : '',
    }));
  }

  async function handleSubmit(e) {
    e.preventDefault();

    setTouched({ name: true, docker_image: true, command: true, vram_required_mb: true });

    if (hasErrors || submitting || submitted) return;

    setSubmitting(true);
    setSubmitError(null);
    setSubmitted(true);

    try {
      const isDocker = form.workload_type === 'docker';
      const job = await createJob({
        name:             form.name.trim(),
        workload_type:    form.workload_type,
        docker_image:     isDocker ? form.docker_image.trim() : null,
        command:          form.command.trim(),
        vram_required_mb: Number(form.vram_required_mb),
        requirements: {
          workload_type: form.workload_type,
          required_vram_mb: Number(form.vram_required_mb),
          ...(isDocker && form.docker_image ? { docker_image: form.docker_image.trim() } : {}),
        },
      });
      navigate(`/jobs/${job.id}`);
    } catch (err) {
      setSubmitError(err);
      setSubmitted(false);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <PageLayout
      title="Submit Job"
      description="Configure a GPU workload and submit it to the CrowdGPU network."
      actions={
        <Link to="/jobs" className="text-sm text-gray-400 hover:text-white transition-colors">
          ← Back to jobs
        </Link>
      }
    >
      <div className="max-w-2xl">
        <form id="form-submit-job" onSubmit={handleSubmit} noValidate className="space-y-6">

          {/* ── Workload Type Selector ────────────────────────────────────── */}
          <div>
            <label className="block text-sm font-medium text-gray-300 mb-2">
              Workload Type <span className="ml-1 text-red-500 text-xs">*</span>
            </label>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              {WORKLOAD_PRESETS.map((preset) => {
                const isSelected = form.workload_type === preset.type;
                return (
                  <button
                    key={preset.type}
                    type="button"
                    onClick={() => handleWorkloadTypeChange(preset.type)}
                    className={`flex flex-col text-left p-3.5 rounded-xl border transition-colors ${
                      isSelected
                        ? 'border-brand-500 bg-brand-950/20 ring-1 ring-brand-500/50'
                        : 'border-gray-800 bg-gray-900/60 hover:bg-gray-800/60'
                    }`}
                  >
                    <div className="flex items-center justify-between w-full">
                      <span className={`text-sm font-semibold ${isSelected ? 'text-brand-300' : 'text-white'}`}>
                        {preset.name}
                      </span>
                      {isSelected && (
                        <span className="h-2 w-2 rounded-full bg-brand-500" />
                      )}
                    </div>
                    <span className="text-xs text-gray-400 mt-1">
                      {preset.description}
                    </span>
                  </button>
                );
              })}
            </div>
          </div>

          {/* ── Job Name ─────────────────────────────────────────────────── */}
          <Field
            label="Job Name"
            htmlFor="job-name"
            hint="A short, descriptive name for this workload."
            error={touched.name ? errors.name : undefined}
          >
            <input
              id="job-name"
              name="name"
              type="text"
              autoComplete="off"
              placeholder="e.g. PyTorch Matrix Multiplication"
              value={form.name}
              onChange={handleChange}
              onBlur={handleBlur}
              className={inputCls(touched.name && errors.name)}
            />
          </Field>

          {/* ── Docker Image (only if docker workload) ───────────────────── */}
          {form.workload_type === 'docker' && (
            <Field
              label="Docker Image"
              htmlFor="job-docker-image"
              hint="Container image that will be pulled and executed on the provider GPU."
              error={touched.docker_image ? errors.docker_image : undefined}
            >
              <input
                id="job-docker-image"
                name="docker_image"
                type="text"
                autoComplete="off"
                placeholder="e.g. pytorch/pytorch:latest"
                value={form.docker_image}
                onChange={handleChange}
                onBlur={handleBlur}
                className={`${inputCls(touched.docker_image && errors.docker_image)} font-mono`}
              />
            </Field>
          )}

          {/* ── Command ───────────────────────────────────────────────────── */}
          <Field
            label="Workload Command / Target"
            htmlFor="job-command"
            hint={
              form.workload_type === 'docker'
                ? 'Entrypoint command to execute inside the container.'
                : 'Built-in CUDA execution routine.'
            }
            error={touched.command ? errors.command : undefined}
          >
            <input
              id="job-command"
              name="command"
              type="text"
              autoComplete="off"
              placeholder="e.g. matrix_multiply"
              value={form.command}
              onChange={handleChange}
              onBlur={handleBlur}
              className={`${inputCls(touched.command && errors.command)} font-mono`}
            />
          </Field>

          {/* ── Required VRAM ─────────────────────────────────────────────── */}
          <Field
            label="Minimum VRAM Required"
            htmlFor="job-vram"
            hint="The scheduler will match provider peers having at least this much GPU memory."
            error={touched.vram_required_mb ? errors.vram_required_mb : undefined}
          >
            <select
              id="job-vram"
              name="vram_required_mb"
              value={form.vram_required_mb}
              onChange={handleChange}
              onBlur={handleBlur}
              className={inputCls(touched.vram_required_mb && errors.vram_required_mb)}
            >
              {VRAM_OPTIONS.map((o) => (
                <option key={o.value} value={o.value}>{o.label}</option>
              ))}
            </select>
          </Field>

          {/* ── Auth notice ───────────────────────────────────────────────── */}
          <div className="rounded-lg border border-brand-900/40 bg-brand-950/20 px-4 py-3">
            <p className="text-xs text-brand-300">
              <strong>Execution Target:</strong> Workloads are assigned by the Coordinator scheduler to matching active GPU workers.
            </p>
          </div>

          {/* ── Submit error ──────────────────────────────────────────────── */}
          {submitError && (
            <div
              role="alert"
              className="rounded-lg border border-red-900/50 bg-red-950/30 px-4 py-3 text-sm text-red-400"
            >
              {submitError.message}
            </div>
          )}

          {/* ── Actions ───────────────────────────────────────────────────── */}
          <div className="flex items-center gap-4 pt-2">
            <button
              type="submit"
              id="btn-submit-job"
              disabled={submitting || submitted}
              aria-busy={submitting}
              className="inline-flex items-center gap-2 rounded-md bg-brand-600 px-5 py-2 text-sm font-medium text-white hover:bg-brand-500 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              {submitting && (
                <svg className="h-3.5 w-3.5 animate-spin" viewBox="0 0 24 24" fill="none" aria-hidden="true">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z" />
                </svg>
              )}
              {submitting ? 'Submitting…' : 'Submit Job'}
            </button>

            <Link
              to="/jobs"
              className="text-sm text-gray-400 hover:text-white transition-colors"
            >
              Cancel
            </Link>
          </div>
        </form>
      </div>
    </PageLayout>
  );
}

// ── Helpers ──────────────────────────────────────────────────────────────────

function inputCls(hasError) {
  return [
    'w-full rounded-lg border px-3 py-2 text-sm text-white placeholder-gray-500 bg-gray-800',
    'focus:outline-none focus:ring-1 transition-colors',
    hasError
      ? 'border-red-600 focus:border-red-500 focus:ring-red-500/30'
      : 'border-gray-700 focus:border-brand-500 focus:ring-brand-500',
  ].join(' ');
}

function Field({ label, htmlFor, hint, error, children }) {
  return (
    <div>
      <label htmlFor={htmlFor} className="block text-sm font-medium text-gray-300 mb-1.5">
        {label}
        <span className="ml-1 text-red-500 text-xs">*</span>
      </label>
      {children}
      {error ? (
        <p id={`${htmlFor}-error`} role="alert" className="mt-1.5 text-xs text-red-400">
          {error}
        </p>
      ) : hint ? (
        <p className="mt-1.5 text-xs text-gray-500">{hint}</p>
      ) : null}
    </div>
  );
}
