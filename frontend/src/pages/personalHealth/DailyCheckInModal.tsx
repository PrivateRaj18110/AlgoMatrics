import { useState } from "react";

import {
  Button,
  ConfirmDialog,
  Field,
  Input,
  Modal,
  Textarea,
} from "@/components/ui";
import { getWorkoutPlanForDay } from "@/lib/personalHealthCalculations";
import { usePersonalHealth } from "@/stores/personalHealth";
import { toastSuccess } from "@/stores/toast";
import type { HealthDayRecord } from "@/types/personalHealth";

interface DailyCheckInModalProps {
  open: boolean;
  onClose: () => void;
  initialDate: string;
}

interface DailyCheckInFormProps {
  initialDate: string;
  onClose: () => void;
}

function DailyCheckInForm({ initialDate, onClose }: DailyCheckInFormProps) {
  const getDayRecord = usePersonalHealth((s) => s.getDayRecord);
  const saveDayRecord = usePersonalHealth((s) => s.saveDayRecord);
  const deleteDayRecord = usePersonalHealth((s) => s.deleteDayRecord);

  const [date, setDate] = useState(initialDate);

  const initialRecord = getDayRecord(initialDate);

  const [weightKg, setWeightKg] = useState(
    initialRecord?.weightKg !== undefined ? String(initialRecord.weightKg) : "",
  );
  const [caloriesConsumed, setCaloriesConsumed] = useState(
    initialRecord?.caloriesConsumed !== undefined ? String(initialRecord.caloriesConsumed) : "",
  );
  const [cyclingKm, setCyclingKm] = useState(
    initialRecord?.cyclingKm !== undefined ? String(initialRecord.cyclingKm) : "",
  );
  const [walkingSteps, setWalkingSteps] = useState(
    initialRecord?.walkingSteps !== undefined ? String(initialRecord.walkingSteps) : "",
  );
  const [runningKm, setRunningKm] = useState(
    initialRecord?.runningKm !== undefined ? String(initialRecord.runningKm) : "",
  );

  const [strengthCompleted, setStrengthCompleted] = useState(
    !!initialRecord?.strengthCompleted,
  );
  const [pushUps, setPushUps] = useState(
    initialRecord?.pushUps !== undefined ? String(initialRecord.pushUps) : "",
  );
  const [crunches, setCrunches] = useState(
    initialRecord?.crunches !== undefined ? String(initialRecord.crunches) : "",
  );
  const [squats, setSquats] = useState(
    initialRecord?.squats !== undefined ? String(initialRecord.squats) : "",
  );
  const [lunges, setLunges] = useState(
    initialRecord?.lunges !== undefined ? String(initialRecord.lunges) : "",
  );
  const [plankSeconds, setPlankSeconds] = useState(
    initialRecord?.plankSeconds !== undefined ? String(initialRecord.plankSeconds) : "",
  );

  const [sleepHours, setSleepHours] = useState(
    initialRecord?.sleepHours !== undefined ? String(initialRecord.sleepHours) : "",
  );
  const [waterLiters, setWaterLiters] = useState(
    initialRecord?.waterLiters !== undefined ? String(initialRecord.waterLiters) : "",
  );
  const [energyLevel, setEnergyLevel] = useState<number | undefined>(
    initialRecord?.energyLevel,
  );
  const [sorenessLevel, setSorenessLevel] = useState<number | undefined>(
    initialRecord?.sorenessLevel,
  );

  const [recoveryNotes, setRecoveryNotes] = useState(initialRecord?.recoveryNotes || "");
  const [notes, setNotes] = useState(initialRecord?.notes || "");

  const [confirmDeleteOpen, setConfirmDeleteOpen] = useState(false);

  function handleDateChange(newDate: string) {
    setDate(newDate);
    const existing = getDayRecord(newDate);
    if (existing) {
      setWeightKg(existing.weightKg !== undefined ? String(existing.weightKg) : "");
      setCaloriesConsumed(existing.caloriesConsumed !== undefined ? String(existing.caloriesConsumed) : "");
      setCyclingKm(existing.cyclingKm !== undefined ? String(existing.cyclingKm) : "");
      setWalkingSteps(existing.walkingSteps !== undefined ? String(existing.walkingSteps) : "");
      setRunningKm(existing.runningKm !== undefined ? String(existing.runningKm) : "");
      setStrengthCompleted(!!existing.strengthCompleted);
      setPushUps(existing.pushUps !== undefined ? String(existing.pushUps) : "");
      setCrunches(existing.crunches !== undefined ? String(existing.crunches) : "");
      setSquats(existing.squats !== undefined ? String(existing.squats) : "");
      setLunges(existing.lunges !== undefined ? String(existing.lunges) : "");
      setPlankSeconds(existing.plankSeconds !== undefined ? String(existing.plankSeconds) : "");
      setSleepHours(existing.sleepHours !== undefined ? String(existing.sleepHours) : "");
      setWaterLiters(existing.waterLiters !== undefined ? String(existing.waterLiters) : "");
      setEnergyLevel(existing.energyLevel);
      setSorenessLevel(existing.sorenessLevel);
      setRecoveryNotes(existing.recoveryNotes || "");
      setNotes(existing.notes || "");
    } else {
      setWeightKg("");
      setCaloriesConsumed("");
      setCyclingKm("");
      setWalkingSteps("");
      setRunningKm("");
      setStrengthCompleted(false);
      setPushUps("");
      setCrunches("");
      setSquats("");
      setLunges("");
      setPlankSeconds("");
      setSleepHours("");
      setWaterLiters("");
      setEnergyLevel(undefined);
      setSorenessLevel(undefined);
      setRecoveryNotes("");
      setNotes("");
    }
  }

  const plan = getWorkoutPlanForDay(date);
  const currentRecord = getDayRecord(date);

  const num = (v: string) => (v.trim() !== "" && !isNaN(Number(v)) ? Number(v) : undefined);

  function handleSave(e: React.FormEvent) {
    e.preventDefault();

    const record: Partial<HealthDayRecord> & { date: string } = {
      date,
      weightKg: num(weightKg),
      caloriesConsumed: num(caloriesConsumed),
      cyclingKm: num(cyclingKm),
      walkingSteps: num(walkingSteps),
      runningKm: num(runningKm),
      strengthCompleted,
      pushUps: num(pushUps),
      crunches: num(crunches),
      squats: num(squats),
      lunges: num(lunges),
      plankSeconds: num(plankSeconds),
      sleepHours: num(sleepHours),
      waterLiters: num(waterLiters),
      energyLevel,
      sorenessLevel,
      recoveryNotes: recoveryNotes.trim() || undefined,
      notes: notes.trim() || undefined,
    };

    saveDayRecord(record);
    toastSuccess(`Health metrics saved for ${date}`);
    onClose();
  }

  function handleDelete() {
    deleteDayRecord(date);
    toastSuccess(`Record for ${date} deleted`);
    setConfirmDeleteOpen(false);
    onClose();
  }

  return (
    <>
      <form onSubmit={handleSave} className="space-y-6">
        {/* Planned today reminder */}
        <div className="rounded-lg border border-accent-500/20 bg-accent-500/5 p-3 text-xs dark:bg-accent-500/10">
          <span className="font-semibold text-accent-700 dark:text-accent-300">
            {plan.dayOfWeek} Schedule Focus:
          </span>{" "}
          <span className="text-slate-700 dark:text-slate-300">{plan.focus}</span>
          <div className="mt-1 flex flex-wrap gap-2 text-slate-600 dark:text-slate-400">
            <span>🚴‍♂️ Target: {plan.cyclingKm} km</span>
            <span>🚶‍♂️ Target: {plan.walkingSteps.toLocaleString()} steps</span>
            {plan.runningKm > 0 && <span>🏃‍♂️ Target: {plan.runningKm} km</span>}
            {plan.hasStrength && <span>💪 Strength: {plan.strengthType}</span>}
          </div>
        </div>

        {/* Date Selector */}
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <Field label="Check-In Date" required>
            <Input
              type="date"
              value={date}
              onChange={(e) => handleDateChange(e.target.value)}
            />
          </Field>
          <Field label="Morning Weight (kg)" hint="e.g. 69.8">
            <Input
              type="number"
              step="0.1"
              placeholder="70.0"
              value={weightKg}
              onChange={(e) => setWeightKg(e.target.value)}
            />
          </Field>
        </div>

        {/* Cardio & Nutrition */}
        <div className="space-y-2">
          <h4 className="text-xs font-semibold tracking-wider text-slate-500 uppercase dark:text-slate-400">
            Cardio & Nutrition
          </h4>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-4">
            <Field label="Calories (kcal)" hint="Target: 1,600">
              <Input
                type="number"
                placeholder="1600"
                value={caloriesConsumed}
                onChange={(e) => setCaloriesConsumed(e.target.value)}
              />
            </Field>
            <Field label="Cycling (km)" hint="Target: 20 km">
              <Input
                type="number"
                step="0.5"
                placeholder="20"
                value={cyclingKm}
                onChange={(e) => setCyclingKm(e.target.value)}
              />
            </Field>
            <Field label="Walking (steps)" hint="Target: 5,000">
              <Input
                type="number"
                placeholder="5000"
                value={walkingSteps}
                onChange={(e) => setWalkingSteps(e.target.value)}
              />
            </Field>
            <Field label="Running (km)" hint={plan.runningKm ? `Target: ${plan.runningKm} km` : "Optional"}>
              <Input
                type="number"
                step="0.5"
                placeholder={plan.runningKm ? String(plan.runningKm) : "0"}
                value={runningKm}
                onChange={(e) => setRunningKm(e.target.value)}
              />
            </Field>
          </div>
        </div>

        {/* Strength & Core Section */}
        <div className="space-y-3 rounded-lg border border-slate-200 bg-slate-50/50 p-4 dark:border-surface-800 dark:bg-surface-850/50">
          <div className="flex items-center justify-between">
            <div>
              <h4 className="text-xs font-semibold tracking-wider text-slate-700 uppercase dark:text-slate-300">
                Strength & Core
              </h4>
              <p className="text-xs text-slate-500 dark:text-slate-400">
                {plan.hasStrength ? `Planned: ${plan.strengthType}` : "Cardio / Rest day focus"}
              </p>
            </div>
            <label className="flex items-center gap-2 text-xs font-medium text-slate-700 cursor-pointer dark:text-slate-300">
              <input
                type="checkbox"
                checked={strengthCompleted}
                onChange={(e) => setStrengthCompleted(e.target.checked)}
                className="size-4 rounded border-slate-300 text-accent-600 focus:ring-accent-500"
              />
              Session Completed
            </label>
          </div>

          <div className="grid grid-cols-2 gap-3 sm:grid-cols-5">
            <Field label="Push-ups (reps)">
              <Input
                type="number"
                placeholder="15"
                value={pushUps}
                onChange={(e) => setPushUps(e.target.value)}
              />
            </Field>
            <Field label="Crunches (reps)">
              <Input
                type="number"
                placeholder="20"
                value={crunches}
                onChange={(e) => setCrunches(e.target.value)}
              />
            </Field>
            <Field label="Squats (reps)">
              <Input
                type="number"
                placeholder="15"
                value={squats}
                onChange={(e) => setSquats(e.target.value)}
              />
            </Field>
            <Field label="Lunges (each)">
              <Input
                type="number"
                placeholder="10"
                value={lunges}
                onChange={(e) => setLunges(e.target.value)}
              />
            </Field>
            <Field label="Plank (seconds)">
              <Input
                type="number"
                placeholder="45"
                value={plankSeconds}
                onChange={(e) => setPlankSeconds(e.target.value)}
              />
            </Field>
          </div>
        </div>

        {/* Recovery & Wellness */}
        <div className="space-y-3">
          <h4 className="text-xs font-semibold tracking-wider text-slate-500 uppercase dark:text-slate-400">
            Sleep & Recovery
          </h4>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <Field label="Sleep (hours)">
              <Input
                type="number"
                step="0.5"
                placeholder="7.5"
                value={sleepHours}
                onChange={(e) => setSleepHours(e.target.value)}
              />
            </Field>
            <Field label="Water Intake (liters)">
              <Input
                type="number"
                step="0.5"
                placeholder="3.0"
                value={waterLiters}
                onChange={(e) => setWaterLiters(e.target.value)}
              />
            </Field>
          </div>

          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <div>
              <label className="mb-1.5 block text-xs font-medium uppercase text-slate-600 dark:text-slate-400">
                Energy Level ({energyLevel ? `${energyLevel}/10` : "Not set"})
              </label>
              <div className="flex gap-1">
                {[1, 2, 3, 4, 5, 6, 7, 8, 9, 10].map((numVal) => (
                  <button
                    key={numVal}
                    type="button"
                    onClick={() => setEnergyLevel(numVal)}
                    className={`flex-1 rounded py-1 text-xs font-medium transition-colors ${
                      energyLevel === numVal
                        ? "bg-accent-600 text-white"
                        : "bg-slate-100 text-slate-600 hover:bg-slate-200 dark:bg-surface-800 dark:text-slate-300 dark:hover:bg-surface-700"
                    }`}
                  >
                    {numVal}
                  </button>
                ))}
              </div>
            </div>

            <div>
              <label className="mb-1.5 block text-xs font-medium uppercase text-slate-600 dark:text-slate-400">
                Muscle Soreness ({sorenessLevel ? `${sorenessLevel}/10` : "Not set"})
              </label>
              <div className="flex gap-1">
                {[1, 2, 3, 4, 5, 6, 7, 8, 9, 10].map((numVal) => (
                  <button
                    key={numVal}
                    type="button"
                    onClick={() => setSorenessLevel(numVal)}
                    className={`flex-1 rounded py-1 text-xs font-medium transition-colors ${
                      sorenessLevel === numVal
                        ? "bg-amber-600 text-white"
                        : "bg-slate-100 text-slate-600 hover:bg-slate-200 dark:bg-surface-800 dark:text-slate-300 dark:hover:bg-surface-700"
                    }`}
                  >
                    {numVal}
                  </button>
                ))}
              </div>
            </div>
          </div>
        </div>

        {/* Notes */}
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <Field label="Recovery / Mobility Notes">
            <Textarea
              rows={2}
              placeholder="Foam rolling, stretching, hydration notes..."
              value={recoveryNotes}
              onChange={(e) => setRecoveryNotes(e.target.value)}
            />
          </Field>
          <Field label="Workout & General Notes">
            <Textarea
              rows={2}
              placeholder="How the workout felt, energy, pacing..."
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
            />
          </Field>
        </div>

        {/* Actions */}
        <div className="flex items-center justify-between border-t border-slate-200 pt-4 dark:border-surface-800">
          {currentRecord ? (
            <Button
              variant="danger"
              size="sm"
              onClick={() => setConfirmDeleteOpen(true)}
            >
              Delete Day
            </Button>
          ) : (
            <div />
          )}

          <div className="flex items-center gap-2">
            <Button variant="secondary" onClick={onClose}>
              Cancel
            </Button>
            <Button type="submit" variant="primary" className="px-6 font-bold shadow-md">
              SAVE DAY
            </Button>
          </div>
        </div>
      </form>

      <ConfirmDialog
        open={confirmDeleteOpen}
        title="Delete Health Record"
        body={`Are you sure you want to delete the health record for ${date}? This action cannot be undone.`}
        confirmLabel="Delete"
        danger
        onConfirm={handleDelete}
        onClose={() => setConfirmDeleteOpen(false)}
      />
    </>
  );
}

export function DailyCheckInModal({
  open,
  onClose,
  initialDate,
}: DailyCheckInModalProps) {
  if (!open) return null;

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={`Daily Check-In — ${initialDate}`}
      wide
    >
      <DailyCheckInForm
        key={`${initialDate}-${open}`}
        initialDate={initialDate}
        onClose={onClose}
      />
    </Modal>
  );
}
