import type { QueueData } from "@/lib/types";
import type { BackendOptimize, BackendQueue } from "./backend-types";
import { adaptCaseSummary } from "./case.adapter";

/** GET /queue (ranked cases) + POST /queue/optimize (capacity selection) -> the queue screen's data. */
export function adaptQueue(queue: BackendQueue, plan: BackendOptimize): QueueData {
  return {
    capacityHours: plan.capacity,
    usedHours: plan.total_hours,
    selected: plan.selected_cases.map((c) => c.case_id),
    total: queue.total,
    expectedRecovery: plan.total_expected_recovery,
    harmReduction: plan.total_harm_reduction,
    cases: queue.cases.map(adaptCaseSummary),
  };
}
