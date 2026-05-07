import { useEffect, useMemo, useState } from "preact/hooks";

import { Text } from "@/design-system";
import { withLocalApiToken } from "@/services/api/client";
import { documents } from "@/services/api/endpoints";

import styles from "./ExcelReader.module.css";

interface ExcelReaderProps {
  docId: string;
}

interface SheetData {
  name: string;
  rows: string[][];
  columnCount: number;
}

type LoadState =
  | { status: "loading" }
  | { status: "ready"; sheets: SheetData[] }
  | { status: "error"; message: string };

/**
 * Excel-style read-only spreadsheet viewer.
 *
 * Strategy: fetch the original .xlsx blob, parse it via SheetJS in the
 * browser, and render each sheet as an HTML table with a sheet-tab bar
 * along the bottom. Supports XLSX, XLS, CSV, TSV (the same parser
 * handles all four).
 *
 * SheetJS is dynamically imported so its ~700 KB only loads when a
 * spreadsheet is actually opened.
 */
export function ExcelReader({ docId }: ExcelReaderProps) {
  const [state, setState] = useState<LoadState>({ status: "loading" });
  const [activeSheet, setActiveSheet] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setState({ status: "loading" });
    setActiveSheet(0);

    (async () => {
      try {
        const url = await withLocalApiToken(documents.fileUrl(docId));
        const response = await fetch(url);
        if (!response.ok) {
          throw new Error(`HTTP ${response.status}`);
        }
        const buffer = await response.arrayBuffer();
        const xlsx = await import("xlsx");
        const workbook = xlsx.read(buffer, { type: "array" });

        const sheets: SheetData[] = workbook.SheetNames.map((name) => {
          const sheet = workbook.Sheets[name];
          if (!sheet) {
            return { name, rows: [], columnCount: 0 };
          }
          // Use header: 1 for an array-of-arrays representation; raw
          // false formats numbers/dates per the cell's display format.
          const rows = xlsx.utils.sheet_to_json<string[]>(sheet, {
            header: 1,
            raw: false,
            defval: ""
          });
          const columnCount = rows.reduce(
            (max, row) => Math.max(max, row.length),
            0
          );
          return { name, rows, columnCount };
        });

        if (cancelled) return;
        setState({ status: "ready", sheets });
      } catch (error) {
        if (cancelled) return;
        const message = error instanceof Error ? error.message : "Unknown error";
        setState({ status: "error", message });
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [docId]);

  const currentSheet = useMemo(() => {
    if (state.status !== "ready") return null;
    return state.sheets[activeSheet] ?? null;
  }, [state, activeSheet]);

  if (state.status === "loading") {
    return (
      <div className={styles.frame}>
        <div className={styles.skeleton}>
          <div className={styles.skeletonRow} />
          <div className={styles.skeletonRow} />
          <div className={styles.skeletonRow} />
        </div>
      </div>
    );
  }

  if (state.status === "error") {
    return (
      <div className={styles.frame}>
        <div className={styles.errorBox}>
          <Text tone="danger">Could not parse this spreadsheet: {state.message}</Text>
        </div>
      </div>
    );
  }

  if (!currentSheet) {
    return (
      <div className={styles.frame}>
        <Text tone="secondary">This workbook has no sheets.</Text>
      </div>
    );
  }

  // Excel-style A, B, C, ..., Z, AA, AB column letters.
  const columnLetter = (index: number): string => {
    let label = "";
    let n = index;
    while (n >= 0) {
      label = String.fromCharCode(65 + (n % 26)) + label;
      n = Math.floor(n / 26) - 1;
    }
    return label;
  };

  const isNumeric = (value: string): boolean => {
    if (value === "" || value === null || value === undefined) return false;
    return /^-?[\d,]+(\.\d+)?$/.test(value.trim());
  };

  return (
    <div className={styles.frame}>
      <div className={styles.gridWrap}>
        <table className={styles.grid}>
          <thead>
            <tr>
              <th className={styles.cornerCell} aria-label="Column header" />
              {Array.from({ length: currentSheet.columnCount }, (_, colIndex) => (
                <th key={colIndex} className={styles.columnHeader}>
                  {columnLetter(colIndex)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {currentSheet.rows.map((row, rowIndex) => (
              <tr key={rowIndex}>
                <th className={styles.rowHeader}>{rowIndex + 1}</th>
                {Array.from({ length: currentSheet.columnCount }, (_, colIndex) => {
                  const value = row[colIndex] ?? "";
                  const numeric = isNumeric(value);
                  return (
                    <td
                      key={colIndex}
                      className={[styles.cell, numeric ? styles.numericCell : ""]
                        .filter(Boolean)
                        .join(" ")}
                    >
                      {value}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {state.sheets.length > 1 ? (
        <div className={styles.sheetTabs}>
          {state.sheets.map((sheet, index) => (
            <button
              key={sheet.name}
              type="button"
              className={[
                styles.sheetTab,
                index === activeSheet ? styles.sheetTabActive : ""
              ]
                .filter(Boolean)
                .join(" ")}
              onClick={() => setActiveSheet(index)}
            >
              {sheet.name}
            </button>
          ))}
        </div>
      ) : null}
    </div>
  );
}
