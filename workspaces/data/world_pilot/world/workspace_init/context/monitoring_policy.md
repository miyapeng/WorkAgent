# Fictional internal monitoring policy

Internal cost-control governance for this pilot: the project manager may approve reallocations within a single work package up to 5 percent of that package's baseline budget and may commit contingency up to 3 percent of total baseline budget without escalation. Reallocations between work packages, any change exceeding 10 percent of a work package baseline, and any baseline date change affecting a downstream dependency require approval by the Network Infrastructure Steering Group. Resource-hour transfers between work-package pools must be documented as an explicit recommendation and approved by the resource owner before being reflected in reporting. Status reporting occurs at each monthly snapshot using baseline-equivalent effort; variances are reported before any corrective action is proposed, and no scope change may be executed on the basis of a forecast alone.

This is a simplified experimental policy, not real law or a claimed industry standard.
All three tables belong to the project and snapshot in project_brief.md; join them by work_package_id. Blank actual_finish means not completed at the snapshot. Dates are calendar dates. planned_completed_effort_hours and completed_effort_hours measure baseline-equivalent work, not actual labor consumed. baseline_budget_usd is the approved total budget per work package. actual_cost_usd includes all incurred expenses through the snapshot, including incurred unpaid items. Remaining commitments are future nonlabor only: exclude incurred expenses and future labor. Remaining labor hours and rates are project-manager estimates, not known future outcomes. Forecasts assume these estimates and rates remain applicable; no additional taxes, overhead or currency conversions. Available remaining hours refer to the same package-specific resource pool and planning horizon as estimated remaining hours. Do not assume spare resources can transfer between packages without approval.

Calculate these per-work-package metrics (USD for *_usd, hours for *_hours):
- cost_variance_to_date_usd: actual_cost_usd - baseline_budget_usd; negative is remaining budget, not proof of savings
- schedule_effort_gap_hours: planned_completed_effort_hours - completed_effort_hours; positive is behind planned effort
- forecast_total_cost_usd: actual_cost_usd + estimated_remaining_hours * hourly_rate_usd + committed_remaining_nonlabor_usd
- forecast_budget_variance_usd: forecast_total_cost_usd - baseline_budget_usd; positive is forecast overrun
- resource_gap_hours: max(0, estimated_remaining_hours - available_remaining_hours)

Discuss overdue incomplete milestones and early/late completed milestones using baseline_due, actual_finish and the snapshot. Explain forecast uncertainty, budget/resource pressures and possible controls. Recommend actions; do not treat a recommendation as already approved.
