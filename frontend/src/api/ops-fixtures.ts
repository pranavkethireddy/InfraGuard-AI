import whatif from './fixtures/contracts/incident.whatif.response.json';
import technicians from './fixtures/contracts/ops.technicians.response.json';
import plan from './fixtures/contracts/ops.plan.response.json';
import matrix from './fixtures/contracts/learning.matrix.response.json';
import cases from './fixtures/contracts/learning.cases.response.json';
import type { LearningCases, LearningMatrix, PlanResponse, TechniciansResponse, WhatIfResponse } from './ops-types';
// JSON imports widen enum literals, but all nested keys/nullability/numbers remain checked.
export type JsonShape<T> = T extends string ? string : T extends (infer U)[] ? JsonShape<U>[] : T extends object ? { [K in keyof T]: JsonShape<T[K]> } : T;
const checkedWhatIf: JsonShape<WhatIfResponse> = whatif;
const checkedCrew: JsonShape<TechniciansResponse> = technicians;
const checkedPlan: JsonShape<PlanResponse> = plan;
const checkedMatrix: LearningMatrix = matrix;
const checkedCases: JsonShape<LearningCases> = cases;
void checkedWhatIf; void checkedCrew; void checkedPlan; void checkedCases;
export const opsFixtures = {
  whatif: whatif as WhatIfResponse, technicians: technicians as TechniciansResponse,
  plan: plan as PlanResponse, matrix: checkedMatrix, cases: cases as LearningCases,
};