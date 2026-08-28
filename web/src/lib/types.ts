// Mirrors cloud/whaletale_cloud/api/operator/schemas.py

export type Site = {
  id: string;
  name: string;
  timezone: string;
  status: string;
};

export type Space = {
  id: string;
  name: string;
  kind: string;
  parent_space_id: string | null;
  archived: boolean;
  current_occupant: string | null;
  current_occupant_id: string | null;
};

export type Occupant = {
  id: string;
  name: string;
  contact_email: string | null;
  contact_phone: string | null;
  archived: boolean;
  space_names: string[];
};

export type SpaceMetrics = {
  period_start: string;
  period_end: string;
  entries: number;
  traffic_share: number | null;
  capture_rate: number;
  median_dwell_seconds: number;
  peer_rank: number | null;
  peer_count: number | null;
  entries_is_anomaly: boolean;
  degraded_bucket_count: number;
};

export type OccupancySpan = {
  occupant_name: string | null;
  start: string;
  end: string;
};

export type SpaceDetail = {
  space: Space;
  metrics: SpaceMetrics;
  occupancy: OccupancySpan[];
};

export type ScheduleCell = {
  space_id: string;
  day: string;
  occupant_name: string | null;
};

export type ScheduleGrid = {
  site_id: string;
  days: string[];
  space_ids: string[];
  space_names: Record<string, string>;
  cells: ScheduleCell[];
};

export type OverviewSpaceRow = {
  space_id: string;
  name: string;
  kind: string;
  entries: number;
  capture_rate: number;
  occupant_name: string | null;
  is_vacant: boolean;
};

export type Overview = {
  site: Site;
  period_start: string;
  period_end: string;
  spaces: OverviewSpaceRow[];
  vacant_space_ids: string[];
  boxes_online: number;
  boxes_total: number;
  cameras_offline: string[];
};

export type TenancyOut = {
  id: string;
  space_id: string;
  occupant_id: string;
  occupant_name: string;
  kind: string;
  starts_on: string;
  ends_on: string | null;
  recurrence_rule: string | null;
};

export type ReshapeOut = {
  zone_version_id: string;
  version_number: number;
  previous_version_id: string | null;
  message: string;
};

export type CurrentZone = {
  zone_version_id: string;
  polygon: [number, number][];
  version_number: number;
};

export type Camera = {
  id: string;
  name: string;
  resolution: string;
  fps_target: number;
  status: string;
  last_seen_at: string | null;
};

export type EdgeBox = {
  id: string;
  name: string | null;
  agent_version: string | null;
  last_seen_at: string | null;
  created_at: string;
};

export type BillingStatus = {
  status: string;
  camera_quantity: number;
  billed_cameras: number;
  current_period_end: string | null;
  grace_until: string | null;
  read_only: boolean;
  export_ready_at: string | null;
};

export type ChangePreview = {
  current_cameras: number;
  new_cameras: number;
  prorated_amount_cents: number;
  currency: string;
  next_invoice_total_cents: number;
  effective: string;
  lines: string[];
};
