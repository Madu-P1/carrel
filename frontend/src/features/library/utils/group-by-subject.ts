import type { DocumentRow } from "@/services/api/endpoints";

export function groupBySubject(rows: DocumentRow[]): Record<string, DocumentRow[]> {
  return rows.reduce<Record<string, DocumentRow[]>>((groups, row) => {
    const subject = row.subject_name?.trim() || "General";
    groups[subject] = groups[subject] ? [...groups[subject], row] : [row];
    return groups;
  }, {});
}
