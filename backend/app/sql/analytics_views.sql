-- ============================================================================================
-- NEXORA AI — Power BI / SQL analytics layer (schema `analytics`).
-- Read-only views over the operational tables; connect BI tools with the nexora_bi role
-- (deployment/sql/readonly_role.sql). All metrics are derived from recorded events — nothing is estimated
-- except where a column name ends in _estimate.
-- Apply: psql "$DATABASE_URL" -f database/analytics_views.sql
-- ============================================================================================
CREATE SCHEMA IF NOT EXISTS analytics;

-- Dimension: organisations with current plan
CREATE OR REPLACE VIEW analytics.dim_org AS
SELECT o.id AS org_id, o.name, o.industry, o.size, o.created_at::date AS signup_date, s.plan, s.status AS subscription_status, s.provider AS billing_provider,
       (o.deleted_at IS NOT NULL) AS is_deleted
FROM organizations o LEFT JOIN subscriptions s ON s.org_id = o.id;

-- Fact: product events (Mixpanel-compatible taxonomy)
CREATE OR REPLACE VIEW analytics.fact_events AS
SELECT e.id AS event_id, e.org_id, e.user_id, e.event, e.created_at, e.created_at::date AS event_date,
       date_trunc('week', e.created_at)::date AS event_week, e.properties->>'outcome_type' AS outcome_type
FROM analytics_events e;

-- North Star Metric: weekly successful AI-assisted business outcomes, per organisation
CREATE OR REPLACE VIEW analytics.north_star_weekly AS
SELECT date_trunc('week', created_at)::date AS week, org_id, count(*) AS outcomes,
       count(DISTINCT user_id) AS users_with_outcome
FROM analytics_events WHERE event = 'outcome_achieved' GROUP BY 1, 2;

-- Activation funnel per signup cohort week
CREATE OR REPLACE VIEW analytics.activation_funnel AS
WITH s AS (SELECT user_id, min(created_at) AS t0 FROM analytics_events WHERE event = 'user_signed_up' GROUP BY 1),
f AS (
  SELECT s.user_id, date_trunc('week', s.t0)::date AS cohort_week,
    min(e.created_at) FILTER (WHERE e.event = 'document_uploaded') AS first_doc,
    min(e.created_at) FILTER (WHERE e.event = 'ai_query_completed') AS first_ai,
    min(e.created_at) FILTER (WHERE e.event = 'workflow_completed') AS first_workflow,
    min(e.created_at) FILTER (WHERE e.event = 'outcome_achieved') AS first_outcome, s.t0
  FROM s LEFT JOIN analytics_events e ON e.user_id = s.user_id GROUP BY s.user_id, s.t0)
SELECT cohort_week, count(*) AS signups, count(first_doc) AS uploaded_doc, count(first_ai) AS asked_ai,
       count(first_workflow) AS completed_workflow, count(first_outcome) AS achieved_outcome,
       percentile_cont(0.5) WITHIN GROUP (ORDER BY extract(epoch FROM first_outcome - t0) / 60) AS median_minutes_to_first_value
FROM f GROUP BY cohort_week;

-- Retention: share of a signup cohort active in day windows 7-13, 30-36, 90-96
CREATE OR REPLACE VIEW analytics.retention_cohorts AS
WITH s AS (SELECT user_id, min(created_at) AS t0 FROM analytics_events WHERE event = 'user_signed_up' GROUP BY 1)
SELECT date_trunc('week', s.t0)::date AS cohort_week, count(*) AS users,
  count(*) FILTER (WHERE EXISTS (SELECT 1 FROM analytics_events e WHERE e.user_id = s.user_id AND e.created_at >= s.t0 + interval '7 days' AND e.created_at < s.t0 + interval '14 days')) AS d7_active,
  count(*) FILTER (WHERE EXISTS (SELECT 1 FROM analytics_events e WHERE e.user_id = s.user_id AND e.created_at >= s.t0 + interval '30 days' AND e.created_at < s.t0 + interval '37 days')) AS d30_active,
  count(*) FILTER (WHERE EXISTS (SELECT 1 FROM analytics_events e WHERE e.user_id = s.user_id AND e.created_at >= s.t0 + interval '90 days' AND e.created_at < s.t0 + interval '97 days')) AS d90_active
FROM s GROUP BY 1;

-- AI cost & quality per day, model and feature (unit economics input)
CREATE OR REPLACE VIEW analytics.ai_usage_daily AS
SELECT created_at::date AS day, org_id, provider, model, feature, task_type, count(*) AS requests,
       sum(input_tokens) AS input_tokens, sum(output_tokens) AS output_tokens, sum(cached_tokens) AS cached_tokens,
       sum(cost_usd) AS cost_usd, avg(latency_ms) AS avg_latency_ms,
       count(*) FILTER (WHERE status = 'error') AS errors, count(*) FILTER (WHERE fallback_used) AS fallbacks,
       count(*) FILTER (WHERE cache_hit) AS cache_hits
FROM ai_requests GROUP BY 1, 2, 3, 4, 5, 6;

-- Cost per successful outcome (the AI unit-economics KPI)
CREATE OR REPLACE VIEW analytics.cost_per_outcome_weekly AS
SELECT w.week, w.org_id, w.outcomes, coalesce(c.cost_usd, 0) AS ai_cost_usd,
       CASE WHEN w.outcomes > 0 THEN coalesce(c.cost_usd, 0) / w.outcomes END AS cost_per_outcome_usd
FROM analytics.north_star_weekly w
LEFT JOIN (SELECT date_trunc('week', created_at)::date AS week, org_id, sum(cost_usd) AS cost_usd FROM ai_requests GROUP BY 1, 2) c
  ON c.week = w.week AND c.org_id = w.org_id;

-- Workflow reliability
CREATE OR REPLACE VIEW analytics.workflow_reliability_daily AS
SELECT x.created_at::date AS day, x.org_id, w.name AS workflow, x.trigger, count(*) AS executions,
       count(*) FILTER (WHERE x.status = 'succeeded') AS succeeded, count(*) FILTER (WHERE x.status = 'failed') AS failed,
       avg(x.duration_ms) FILTER (WHERE x.duration_ms IS NOT NULL) AS avg_duration_ms
FROM workflow_executions x JOIN workflows w ON w.id = x.workflow_id GROUP BY 1, 2, 3, 4;

-- Feature adoption (weekly active users per module)
CREATE OR REPLACE VIEW analytics.feature_adoption_weekly AS
SELECT date_trunc('week', created_at)::date AS week, org_id,
  count(DISTINCT user_id) AS wau,
  count(DISTINCT user_id) FILTER (WHERE event = 'ai_query_completed') AS assistant_users,
  count(DISTINCT user_id) FILTER (WHERE event = 'document_uploaded') AS knowledge_users,
  count(DISTINCT user_id) FILTER (WHERE event = 'agent_executed') AS agent_users,
  count(DISTINCT user_id) FILTER (WHERE event IN ('workflow_executed','workflow_published')) AS workflow_users,
  count(DISTINCT user_id) FILTER (WHERE event = 'dataset_queried') AS data_users,
  count(DISTINCT user_id) FILTER (WHERE event = 'task_created') AS task_users
FROM analytics_events WHERE user_id IS NOT NULL GROUP BY 1, 2;

-- Revenue: MRR by plan from subscriptions (list prices; demo-billed subscriptions flagged)
CREATE OR REPLACE VIEW analytics.mrr_by_plan AS
SELECT plan, provider AS billing_provider, count(*) AS active_subscriptions,
       count(*) * CASE plan WHEN 'starter' THEN 49 WHEN 'professional' THEN 199 ELSE 0 END AS mrr_usd_list_price,
       (provider <> 'stripe') AS is_demo_or_manual
FROM subscriptions WHERE status = 'active' GROUP BY plan, provider;

-- Experiment exposure & conversion (results only meaningful with real traffic)
CREATE OR REPLACE VIEW analytics.experiment_exposure AS
SELECT a.experiment_key, a.variant, count(DISTINCT a.subject_id) AS subjects,
       count(DISTINCT e.user_id) FILTER (WHERE e.event = 'outcome_achieved') AS converted_users
FROM experiment_assignments a LEFT JOIN analytics_events e ON e.user_id::text = a.subject_id
GROUP BY 1, 2;
