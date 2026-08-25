import { useRef, useState } from "react";

import { Button, Card, ConfirmDialog, Field, Input } from "@/components/ui";
import { exportToCSV, importFromCSV } from "@/lib/personalHealthCalculations";
import { usePersonalHealth } from "@/stores/personalHealth";
import { toastError, toastSuccess } from "@/stores/toast";
import type { HealthDayRecord } from "@/types/personalHealth";

export function PersonalHealthSettingsTab() {
  const config = usePersonalHealth((s) => s.config);
  const updateConfig = usePersonalHealth((s) => s.updateConfig);
  const resetProgram = usePersonalHealth((s) => s.resetProgram);
  const importRecords = usePersonalHealth((s) => s.importRecords);
  const getAllRecordsList = usePersonalHealth((s) => s.getAllRecordsList);

  const [startingWeight, setStartingWeight] = useState(String(config.startingWeightKg));
  const [targetWeight, setTargetWeight] = useState(String(config.targetWeightKg));
  const [heightCm, setHeightCm] = useState(String(config.heightCm));
  const [dailyCalories, setDailyCalories] = useState(String(config.dailyCaloriesTarget));
  const [dailyCycling, setDailyCycling] = useState(String(config.dailyCyclingKmTarget));
  const [dailyWalking, setDailyWalking] = useState(String(config.dailyWalkingStepsTarget));
  const [weeklyRunning, setWeeklyRunning] = useState(String(config.weeklyRunningKmTarget));
  const [weeklyStrength, setWeeklyStrength] = useState(String(config.weeklyStrengthSessionsTarget));
  const [startDate, setStartDate] = useState(config.startDate);
  const [endDate, setEndDate] = useState(config.endDate);

  const [confirmResetOpen, setConfirmResetOpen] = useState(false);
  const [confirmImportOpen, setConfirmImportOpen] = useState(false);
  const [pendingImportData, setPendingImportData] = useState<HealthDayRecord[] | null>(null);

  const fileInputRef = useRef<HTMLInputElement>(null);

  function handleSaveTargets(e: React.FormEvent) {
    e.preventDefault();

    updateConfig({
      startingWeightKg: Number(startingWeight) || 70,
      targetWeightKg: Number(targetWeight) || 60,
      heightCm: Number(heightCm) || 165,
      dailyCaloriesTarget: Number(dailyCalories) || 1600,
      dailyCyclingKmTarget: Number(dailyCycling) || 20,
      dailyWalkingStepsTarget: Number(dailyWalking) || 5000,
      weeklyRunningKmTarget: Number(weeklyRunning) || 20,
      weeklyStrengthSessionsTarget: Number(weeklyStrength) || 3,
      startDate,
      endDate,
    });

    toastSuccess("Program settings updated successfully");
  }

  function handleExportCSV() {
    const list = getAllRecordsList();
    const csvContent = exportToCSV(list, config);
    const blob = new Blob([csvContent], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.setAttribute("href", url);
    link.setAttribute("download", `algomatrics_personal_health_${new Date().toISOString().slice(0, 10)}.csv`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    toastSuccess("CSV exported successfully");
  }

  function handleFileSelect(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;

    const reader = new FileReader();
    reader.onload = (event) => {
      const text = event.target?.result as string;
      const res = importFromCSV(text);
      if (!res.success || !res.records) {
        toastError("Import Failed", res.error || "Invalid CSV format");
        return;
      }
      setPendingImportData(res.records);
      setConfirmImportOpen(true);
    };
    reader.readAsText(file);
    if (fileInputRef.current) fileInputRef.current.value = "";
  }

  function handleConfirmImport() {
    if (pendingImportData) {
      importRecords(pendingImportData, false);
      toastSuccess(`Successfully imported ${pendingImportData.length} records`);
    }
    setConfirmImportOpen(false);
    setPendingImportData(null);
  }

  function handleReset() {
    resetProgram();
    setStartingWeight("70");
    setTargetWeight("60");
    setHeightCm("165");
    setDailyCalories("1600");
    setDailyCycling("20");
    setDailyWalking("5000");
    setWeeklyRunning("20");
    setWeeklyStrength("3");
    setStartDate("2026-08-25");
    setEndDate("2026-11-30");
    setConfirmResetOpen(false);
    toastSuccess("Program reset to initial default state");
  }

  return (
    <div className="space-y-6">
      {/* Target Parameters Form */}
      <Card title="Program Targets & Body Profile">
        <form onSubmit={handleSaveTargets} className="space-y-6">
          <p className="text-xs text-slate-500">
            Configure your personal weight targets and daily fitness goals. Modifying targets will not alter historical recorded entries.
          </p>

          <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
            <Field label="Starting Weight (kg)">
              <Input
                type="number"
                step="0.1"
                value={startingWeight}
                onChange={(e) => setStartingWeight(e.target.value)}
              />
            </Field>
            <Field label="Target Weight (kg)">
              <Input
                type="number"
                step="0.1"
                value={targetWeight}
                onChange={(e) => setTargetWeight(e.target.value)}
              />
            </Field>
            <Field label="Height (cm)">
              <Input
                type="number"
                value={heightCm}
                onChange={(e) => setHeightCm(e.target.value)}
              />
            </Field>
          </div>

          <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
            <Field label="Daily Calories Target (kcal)">
              <Input
                type="number"
                value={dailyCalories}
                onChange={(e) => setDailyCalories(e.target.value)}
              />
            </Field>
            <Field label="Daily Cycling Target (km)">
              <Input
                type="number"
                value={dailyCycling}
                onChange={(e) => setDailyCycling(e.target.value)}
              />
            </Field>
            <Field label="Daily Walking Target (steps)">
              <Input
                type="number"
                value={dailyWalking}
                onChange={(e) => setDailyWalking(e.target.value)}
              />
            </Field>
          </div>

          <div className="grid grid-cols-1 gap-4 sm:grid-cols-4">
            <Field label="Weekly Running Target (km)">
              <Input
                type="number"
                value={weeklyRunning}
                onChange={(e) => setWeeklyRunning(e.target.value)}
              />
            </Field>
            <Field label="Weekly Strength Sessions">
              <Input
                type="number"
                value={weeklyStrength}
                onChange={(e) => setWeeklyStrength(e.target.value)}
              />
            </Field>
            <Field label="Program Start Date">
              <Input
                type="date"
                value={startDate}
                onChange={(e) => setStartDate(e.target.value)}
              />
            </Field>
            <Field label="Program End Date">
              <Input
                type="date"
                value={endDate}
                onChange={(e) => setEndDate(e.target.value)}
              />
            </Field>
          </div>

          <div className="flex justify-end">
            <Button type="submit" variant="primary">
              Save Settings
            </Button>
          </div>
        </form>
      </Card>

      {/* CSV Import & Export */}
      <Card title="Data Management (CSV Backup & Restore)">
        <div className="space-y-4">
          <p className="text-xs text-slate-500">
            Export all personal health data to a CSV spreadsheet or restore from an existing backup file.
          </p>

          <div className="flex flex-wrap gap-3">
            <Button variant="secondary" onClick={handleExportCSV}>
              📥 Export CSV Backup
            </Button>

            <label className="inline-flex cursor-pointer items-center">
              <Button
                variant="secondary"
                onClick={() => fileInputRef.current?.click()}
              >
                📤 Import CSV File
              </Button>
              <input
                ref={fileInputRef}
                type="file"
                accept=".csv"
                className="hidden"
                onChange={handleFileSelect}
              />
            </label>
          </div>
        </div>
      </Card>

      {/* Reset Program */}
      <Card title="Reset Program">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h4 className="text-sm font-semibold text-loss-600 dark:text-loss-400">
              Reset All Personal Health Data
            </h4>
            <p className="text-xs text-slate-500">
              This will clear all logged daily records and restore the default 70 kg → 60 kg program schedule.
            </p>
          </div>
          <Button variant="danger" onClick={() => setConfirmResetOpen(true)}>
            Reset Program
          </Button>
        </div>
      </Card>

      {/* Confirm Reset Dialog */}
      <ConfirmDialog
        open={confirmResetOpen}
        title="Reset Personal Health Program"
        body="Are you sure you want to reset all health tracking data? All logged daily records, weights, workouts, and calories will be permanently deleted."
        confirmLabel="Yes, Reset Everything"
        danger
        onConfirm={handleReset}
        onClose={() => setConfirmResetOpen(false)}
      />

      {/* Confirm Import Dialog */}
      <ConfirmDialog
        open={confirmImportOpen}
        title="Confirm CSV Data Import"
        body={`Found ${pendingImportData?.length || 0} records in the CSV file. Do you want to merge these records into your Personal Health tracker?`}
        confirmLabel="Import Records"
        onConfirm={handleConfirmImport}
        onClose={() => {
          setConfirmImportOpen(false);
          setPendingImportData(null);
        }}
      />
    </div>
  );
}
