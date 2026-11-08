import floor from './fixtures/contracts/ops.floor.response.json';
import claim from './fixtures/contracts/ops.pager.claim.response.json';
import paged from './fixtures/contracts/ops.pager.paged.response.json';
import walking from './fixtures/contracts/ops.pager.walking.response.json';
import action from './fixtures/contracts/ops.pager.action.request.json';
import type { FloorPlan, PagerActionRequest, PagerView } from './ops-types';
import type { JsonShape } from './ops-fixtures';
const checkedFloor: JsonShape<FloorPlan> = floor;
const checkedClaim: JsonShape<PagerView> = claim;
const checkedPaged: JsonShape<PagerView> = paged;
const checkedWalking: JsonShape<PagerView> = walking;
const checkedAction: JsonShape<PagerActionRequest> = action;
void checkedFloor; void checkedClaim; void checkedPaged; void checkedWalking; void checkedAction;
// Claim/walking/action examples support tests only. Fixture preview never executes a mutation.
export const pagerFixtures = { floor: floor as FloorPlan, paged: paged as PagerView };