import { create } from "zustand";
import { persist } from "zustand/middleware";

import { DEFAULT_PROGRAM_CONFIG } from "@/lib/personalHealthCalculations";
import type { HealthDayRecord, HealthProgramConfig } from "@/types/personalHealth";

interface PersonalHealthState {
  config: HealthProgramConfig;
  records: Record<string, HealthDayRecord>;

  updateConfig: (updates: Partial<HealthProgramConfig>) => void;
  saveDayRecord: (record: Partial<HealthDayRecord> & { date: string }) => void;
  deleteDayRecord: (dateStr: string) => void;
  importRecords: (incomingRecords: HealthDayRecord[], overwrite?: boolean) => void;
  resetProgram: () => void;

  getDayRecord: (dateStr: string) => HealthDayRecord | undefined;
  getAllRecordsList: () => HealthDayRecord[];
}

export const usePersonalHealth = create<PersonalHealthState>()(
  persist(
    (set, get) => ({
      config: DEFAULT_PROGRAM_CONFIG,
      records: {},

      updateConfig: (updates) => {
        set((state) => ({
          config: {
            ...state.config,
            ...updates,
          },
        }));
      },

      saveDayRecord: (record) => {
        set((state) => {
          const existing = state.records[record.date];
          const updated: HealthDayRecord = {
            ...existing,
            ...record,
            date: record.date,
            updatedAt: new Date().toISOString(),
          };

          return {
            records: {
              ...state.records,
              [record.date]: updated,
            },
          };
        });
      },

      deleteDayRecord: (dateStr) => {
        set((state) => {
          const next = { ...state.records };
          delete next[dateStr];
          return { records: next };
        });
      },

      importRecords: (incomingRecords, overwrite = false) => {
        set((state) => {
          const base = overwrite ? {} : { ...state.records };
          for (const r of incomingRecords) {
            if (r.date) {
              base[r.date] = {
                ...base[r.date],
                ...r,
                updatedAt: r.updatedAt || new Date().toISOString(),
              };
            }
          }
          return { records: base };
        });
      },

      resetProgram: () => {
        set({
          config: DEFAULT_PROGRAM_CONFIG,
          records: {},
        });
      },

      getDayRecord: (dateStr) => {
        return get().records[dateStr];
      },

      getAllRecordsList: () => {
        return Object.values(get().records).sort((a, b) => a.date.localeCompare(b.date));
      },
    }),
    {
      name: "algo-matrics-personal-health-v1",
    },
  ),
);
