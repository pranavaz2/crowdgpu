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

// ── VRAM options ─────────────────────────────────────────────────────────────
const VRAM_OPTIONS = [
  { label: '2 GB  — 2,048 MiB',  value: 2048  },
  { label: '4 GB  — 4,096 MiB',  value: 4096  },
  { label: '8 GB  — 8,192 MiB',  value: 8192  },
  { label: '12 GB — 12,288 MiB', value: 12288 },
  { label: '16 GB — 16,384 MiB', value: 16384 },
  { label: '24 GB — 24,576 MiB', value: 24576 },
  { label: '40 GB — 40,960 MiB', value: 40960 },
  { label: '80 GB — 81,920 MiB', value: 81920 },
];

const INITIAL_FORM = {
  name:             '',
  docker_image:     '',
  command:          '',
  vram_required_mb: 4096,
};

// ── Validation rules ─────────────────────────────────────────────────────────
function validate(form) {
  const errors = {};

  if (!form.name.trim()) {
    errors.name = 'Job name is required.';
  } else if (form.name.trim().length > 120) {
    errors.name = 'Job name must be 120 characters or fewer.';
  }

  if (!form.docker_image.trim()) {
    errors.docker_image = 'Docker image is required.';
  } else if (!/^[a-zA-Z0-9][a-zA-Z0-9._/:@-]*$/.test(form.docker_image.trim())) {
    errors.docker_image = 'Enter a valid Docker image reference (e.g. pytorch/pytorch:latest).';
  }

  if (!form.command.trim()) {
    errors.command = 'Command is required.';
  }

  const vram = Number(form.vram_required_mb);
  if (!vram || vram <= 0) {
    errors.vram_required_mb = 'Select a valid VRAM requirement.';
  }

  return errors;
}

export default function SubmitJobPage() {
  const navigate = useNavigate();

  const [form,       setForm]       = useState(INITIAL_FORM);
  const [touched,    setTouched]    = useState({});  // tracks which fields have been blurred
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState(null);
  const [submitted,  setSubmitted]  = useState(false); // guard against double submit

  const errors = validate(form);
  const hasErrors = Object.keys(errors).length > 0;

  // Mark field as touched on blur so errors show after interaction
  function handleBlur(e) {
    setTouched((prev) => ({ ...prev, [e.target.name]: true }));
  }

  function handleChange(e) {
    const { name, value } = e.target;
    setForm((prev) => ({ ...prev, [name]: value }));
  }

  async function handleSubmit(e) {
    e.preventDefault();

    // Show all field errors on submit attempt
    setTouched({ name: true, docker_image: true, command: true, vram_required_mb: true });

    if (hasErrors || submitting || submitted) return;

    setSubmitting(true);
    setSubmitError(null);
    setSubmitted(true);

    try {
      const job = await createJob({
        name:             form.name.trim(),
        docker_image:     form.docker_image.trim(),
        command:          form.command.trim(),
        vram_required_mb: Number(form.vram_required_mb),
        workload_type:    'batch',
      });
      navigate(`/jobs/${job.id}`);
    } catch (err) {
      setSubmitError(err);
      setSubmitted(false); // allow retry on error
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
              placeholder="e.g. MNIST Training Run"
              value={form.name}
              onChange={handleChange}
              onBlur={handleBlur}
              className={inputCls(touched.name && errors.name)}
            />
          </Field>

          {/* ── Docker Image ──────────────────────────────────────────────── */}
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

          {/* ── Command ───────────────────────────────────────────────────── */}
          <Field
            label="Command"
            htmlFor="job-command"
            hint="Entrypoint command to run inside the container."
            error={touched.command ? errors.command : undefined}
          >
            <input
              id="job-command"
              name="command"
              type="text"
              autoComplete="off"
              placeholder="e.g. python train.py --epochs 10"
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
            hint="The scheduler will only assign peers with at least this much GPU memory."
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
          <div className="rounded-lg border border-amber-900/40 bg-amber-950/20 px-4 py-3">
            <p className="text-xs text-amber-500">
              <strong>Note:</strong> Authentication is not yet implemented.
              Jobs are submitted without an owner until the auth system is in place.
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
