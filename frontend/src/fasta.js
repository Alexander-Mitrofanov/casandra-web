const IUPAC_DNA = new Set("ACGTRYSWKMBDHVNacgtryswkmbdhvn".split(""));
const LINE_BREAKS = /\r\n|\n|\r|\v|\f|\u0085|\u2028|\u2029/;
const INLINE_SPACE = /[\t \u00a0]+/g;
const SOURCE_ID = /^[A-Za-z0-9][A-Za-z0-9_.:-]{0,119}$/;

export function normalizeFastaInput(value) {
  return String(value || "").replace(/^\uFEFF+/, "");
}

export function inspectFasta(value, { maxHeaderCharacters = 200 } = {}) {
  let text = normalizeFastaInput(value).trim();
  const records = [];
  const errors = [];
  const sourceIds = new Set();
  let current = null;

  if (!text) {
    return { valid: false, records, recordCount: 0, baseCount: 0, errors: ["Add at least one nucleotide FASTA record."] };
  }
  if (!text.startsWith(">")) text = `>sequence_1\n${text}`;

  for (const [index, raw] of text.split(LINE_BREAKS).entries()) {
    const lineNumber = index + 1;
    const line = raw.trim();
    if (!line) continue;
    if (line.startsWith(">")) {
      const header = line.slice(1).trim();
      const identifier = header.split(/\s+/)[0] || "";
      if (!identifier) errors.push(`Line ${lineNumber}: FASTA header is empty.`);
      if (header.length > maxHeaderCharacters) {
        errors.push(`Line ${lineNumber}: FASTA header exceeds ${maxHeaderCharacters} characters.`);
      }
      if ([...header].some((character) => (character.charCodeAt(0) < 32 && character !== "\t") || character.charCodeAt(0) === 127)) {
        errors.push(`Line ${lineNumber}: FASTA header contains a control character.`);
      }
      if (identifier && !SOURCE_ID.test(identifier)) {
        errors.push(`Line ${lineNumber}: record IDs must start with a letter or digit, contain only letters, digits, dot, underscore, colon, or dash, and be at most 120 characters.`);
      }
      if (sourceIds.has(identifier)) errors.push(`Record identifier “${identifier}” is duplicated.`);
      sourceIds.add(identifier);
      current = { header, identifier, sequence: "" };
      records.push(current);
      continue;
    }

    if (!current) {
      errors.push(`Line ${lineNumber}: sequence appears before a FASTA header.`);
      continue;
    }
    const sequence = line.replace(INLINE_SPACE, "");
    const invalid = [...new Set(sequence)].filter((symbol) => !IUPAC_DNA.has(symbol));
    if (invalid.length) {
      errors.push(`Line ${lineNumber}: unsupported nucleotide symbol${invalid.length === 1 ? "" : "s"} ${invalid.join(", ")}.`);
    }
    current.sequence += sequence.replace(/[a-z]/g, (symbol) => symbol.toUpperCase());
  }

  for (const record of records) {
    if (!record.sequence) errors.push(`Record “${record.identifier || "unnamed"}” has no sequence.`);
  }
  const baseCount = records.reduce((sum, record) => sum + record.sequence.length, 0);
  return {
    valid: records.length > 0 && errors.length === 0,
    records,
    recordCount: records.length,
    baseCount,
    errors: [...new Set(errors)],
  };
}

export function readableBases(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) return "—";
  if (number < 1_000) return `${number.toLocaleString()} bp`;
  if (number < 1_000_000) return `${(number / 1_000).toFixed(number < 10_000 ? 1 : 0)} kbp`;
  return `${(number / 1_000_000).toFixed(number < 10_000_000 ? 2 : 1)} Mbp`;
}
