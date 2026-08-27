export function asArray(value) {
  return Array.isArray(value) ? value : [];
}

export function readableNumber(value) {
  const number = Number(value);
  return Number.isFinite(number) ? number.toLocaleString() : "—";
}

export function readableBytes(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) return "—";
  if (number < 1_024) return `${number.toLocaleString()} B`;
  if (number < 1_048_576) return `${(number / 1_024).toFixed(1)} KiB`;
  if (number < 1_073_741_824) return `${(number / 1_048_576).toFixed(1)} MiB`;
  return `${(number / 1_073_741_824).toFixed(2)} GiB`;
}

export function formatDate(value) {
  if (!value) return "—";
  const date = new Date(value);
  return Number.isFinite(date.getTime())
    ? new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" }).format(date)
    : "—";
}

export function formatDuration(value) {
  const seconds = Number(value);
  if (!Number.isFinite(seconds)) return "—";
  if (seconds < 60) return `${seconds.toFixed(seconds < 10 ? 1 : 0)} s`;
  return `${Math.floor(seconds / 60)} min ${Math.round(seconds % 60)} s`;
}

export function evidenceScore(value, isProbability = false) {
  const number = Number(value);
  if (!Number.isFinite(number)) return "—";
  return isProbability ? `${(number * 100).toFixed(1)}%` : number.toFixed(3);
}

export function downloadName(value, fallback = "casandra-artifact.dat") {
  const cleaned = String(value || "").split(/[\\/]/).pop().replace(/[^A-Za-z0-9._-]+/g, "_");
  return cleaned && cleaned !== "." && cleaned !== ".." ? cleaned.slice(0, 180) : fallback;
}

export function revealSection(id, focusSelector) {
  const section = document.getElementById(id);
  if (!section) return;
  section.scrollIntoView({ behavior: "smooth", block: "start" });
  section.querySelector(focusSelector)?.focus({ preventScroll: true });
}
