import { getJson, sendJson } from "../../api/client";
import type { components } from "../../api/generated";

type S = components["schemas"];

export type MergeProposal = S["MergeProposal"];
export type MergeProposalPage = S["MergeProposalPage"];

const url = (projectId: string, tail = "") => `/api/v1/projects/${projectId}/merge-proposals${tail}`;

export const listMergeProposals = (projectId: string, signal: AbortSignal) =>
  getJson<MergeProposalPage>(`${url(projectId)}?limit=200`, signal);

export type MergeAction = "accept" | "reject" | "revert";

/** Accept applies a revertible merge; nothing is merged without this explicit user action. */
export const decideMergeProposal = (projectId: string, proposalId: string, action: MergeAction, signal?: AbortSignal) =>
  sendJson<MergeProposal>(url(projectId, `/${proposalId}/${action}`), "POST", { decided_by: "user" }, signal);
