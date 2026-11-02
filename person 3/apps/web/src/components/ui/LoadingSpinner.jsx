/**
 * LoadingSpinner — animated loading indicator.
 *
 * Props:
 *   size    — 'sm' | 'md' | 'lg'  (default: 'md')
 *   label   — string (optional) Screen-reader accessible label
 */

const SIZE_CLASSES = {
  sm: 'h-4 w-4 border-2',
  md: 'h-8 w-8 border-2',
  lg: 'h-12 w-12 border-2',
};

/**
 * @param {{ size?: 'sm' | 'md' | 'lg', label?: string }} props
 */
export default function LoadingSpinner({ size = 'md', label = 'Loading…' }) {
  return (
    <div role="status" className="flex items-center justify-center gap-3">
      <div
        className={`${SIZE_CLASSES[size]} animate-spin rounded-full border-gray-700 border-t-brand-500`}
      />
      <span className="sr-only">{label}</span>
    </div>
  );
}
