// SPDX-License-Identifier: GPL-3.0-only
// Copyright (C) 2026  JS8Link contributors

import { useCallback, useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import {
  IconAntennaBars5,
  IconArrowDownLeft,
  IconArrowUpRight,
  IconChartHistogram,
  IconClock,
  IconMail,
  IconMessage,
  IconRadio,
  IconSettings,
  IconWaveSine,
} from "@tabler/icons-react";
import {
  Activity,
  Archive,
  ArchiveRestore,
  ArrowDown,
  ArrowUp,
  ChevronDown,
  ChevronLeft,
  Clock3,
  Database,
  Download,
  Filter,
  MapPin,
  MessagesSquare,
  Palette,
  Pencil,
  Plus,
  Radio,
  ServerCog,
  Search,
  Shield,
  SlidersHorizontal,
  Sun,
  Trash2,
  Settings as SettingsIcon,
  Waypoints,
  X,
} from "lucide-react";
import maplibregl, { type GeoJSONSource, type Map as MapInstance } from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import {
  Button,
  Card,
  Bubble,
  BubbleContent,
  Input,
  Label,
  Message,
  MessageAvatar,
  MessageContent,
  MessageFooter,
  MessageScroller,
  MessageScrollerButton,
  MessageScrollerContent,
  MessageScrollerItem,
  MessageScrollerProvider,
  MessageScrollerViewport,
  MessageGroup,
  MessageHeader,
  HelpButton,
  Select,
  Switch,
  Tabs,
  TabsList,
  TabsTrigger,
  Textarea,
} from "./components";
import { useLanguage } from "./i18n";
import { useTheme, type Theme } from "./theme";
import { useTimeDisplay } from "./time";
import {
  errorMessage,
  averageSnr,
  clampBandScopeMinutes,
  formatDialFrequency,
  filterStationGraph,
  formatOffset,
  parseStoredUtc,
  speedLabel,
  resolveHelpTopicId,
} from "./utils";

type Setup = {
  setup_complete: boolean;
  host: string;
  port: number;
  connected: boolean;
  auth_enabled: boolean;
};
type DiagnosticTraceSummary = {
  trace_id: string;
  source: string;
  event_type: string;
  severity: "info" | "warning" | "error" | string;
  summary: string;
  interpretation: string;
  created_at?: string | null;
};
type DiagnosticProcessing = {
  id: number;
  sequence: number;
  operation: string;
  outcome: string;
  detail: string;
  payload?: string | null;
  created_at?: string | null;
};
type DiagnosticTraceDetail = DiagnosticTraceSummary & {
  raw_payload?: string | null;
  processing: DiagnosticProcessing[];
};
type Status = {
  connected: boolean;
  callsign?: string | null;
  dial?: number | null;
  offset?: number | null;
  speed?: number | null;
  mode_name?: string | null;
  tx_queue_depth?: number;
  station?: { value?: string };
  frequency?: { params?: { DIAL?: number; OFFSET?: number; FREQ?: number } };
  band?: string;
  mode?: { params?: { SPEED?: number } };
  queue?: { params?: { DEPTH?: number } };
  offset_mode?: "auto" | "fixed";
  fixed_offset?: number;
  normal_offset?: number;
  js8call_version?: string;
  rx_enabled?: boolean;
  tx_enabled?: boolean;
};
type ChatSummary = {
  callsign: string;
  last_message: string;
  last_message_at: string;
  last_direction: "rx" | "tx";
  unread_count: number;
  grid?: string;
  last_heard_at?: string;
  last_snr?: number;
  last_offset?: number;
  last_mode?: string;
  js8link_capable?: boolean;
  js8link_version?: number;
  archived?: boolean;
  preferred_speed?: number;
};
type DeliveryMode = "best_effort" | "confirmed";
type ChatMessage = {
  id: string;
  callsign: string;
  from_callsign?: string | null;
  direction: "rx" | "tx";
  text: string;
  timestamp: string;
  status: string;
  band?: string;
  offset?: number;
  mode?: string;
  snr?: number;
  grid?: string;
  delivery_mode?: DeliveryMode;
  delivery_status?: string;
  protocol_id?: string;
  attempts?: number;
};
type ChatStation = {
  callsign: string;
  name?: string;
  qth?: string;
  notes?: string;
  grid?: string;
  last_seen?: string;
  last_snr?: number;
  last_offset?: number;
  last_mode?: string;
  js8link_capable?: boolean;
  js8link_version?: number;
};
type StationContact = {
  callsign: string;
  name?: string | null;
  qth?: string | null;
  notes?: string | null;
};
type JS8Settings = {
  callsign: string;
  grid: string;
  info: string;
  status: string;
  dial: number;
  offset: number;
  offset_mode: "auto" | "fixed";
  fixed_offset: number;
  speed: number;
  spot: boolean;
  js8call_version?: string;
};
type JS8Filter = {
  center: number | null;
  width: number | null;
  enabled: boolean | null;
};
type TxQueueStatus = {
  active: boolean;
  current_message: string | null;
  frames_sent: number;
  estimated_frames: number;
  progress_pct: number;
  queue_depth: number;
  queued_messages: Array<{
    id: number;
    callsign?: string;
    text: string;
    status: string;
    delivery_mode?: string;
  }>;
  timestamp: string;
};
type FrequencyPreset = {
  band: string;
  dial: number;
  frequency_mhz: number;
  label: string;
};
type UpdateInfo = {
  repository: string;
  branch: string;
  current_commit?: string | null;
  latest_commit: string;
  latest_message: string;
  latest_url: string;
  latest_version?: string | null;
  latest_prerelease?: boolean | null;
  platform_artifact?: string | null;
  update_available: boolean;
  can_update: boolean;
  reason?: string | null;
};
type UpdateResult = {
  status: "current" | "updated";
  commit: string;
  restart_scheduled: boolean;
  restart_required?: boolean;
};
type QuerySettings = {
  station_queries_enabled: boolean;
  query_interval_snr_minutes: number;
  query_interval_hearing_minutes: number;
  query_interval_info_days: number;
  query_interval_grid_days: number;
  query_interval_status_hours: number;
  query_max_per_hour: number;
  query_cooldown_seconds: number;
  query_timeout_minutes: number;
};
type ChangelogRelease = {
  version: string;
  date?: string | null;
  categories: Array<{ name: string; items: string[] }>;
};
type SpectrumSignal = {
  offset: number;
  callsign: string;
  snr?: number | null;
  direction: "rx" | "tx";
  mode?: string | null;
  received_at: string;
};
type IncomingToast = {
  id: number;
  callsign: string;
  text: string;
};
type HelpTopic = {
  id: string;
  title: string;
  summary: string;
  sections: Array<{ heading: string; body: string }>;
  steps: string[];
  troubleshooting: string[];
  references: Array<{ label: string; href: string }>;
  related: string[];
};
type HelpCatalog = { language: "nl" | "en"; version: number; topics: HelpTopic[] };

async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, { headers: { "Content-Type": "application/json" }, ...init });
  const body = await response.text();
  if (!response.ok) {
    let detail = body || response.statusText;
    try {
      const parsed = JSON.parse(body) as { detail?: unknown };
      const candidate = parsed.detail ?? detail;
      detail = typeof candidate === "string" ? candidate : JSON.stringify(candidate);
    } catch {
      // Some proxy and server errors are returned as plain text.
    }
    throw new Error(detail);
  }
  return JSON.parse(body) as T;
}

function IncomingMessageToast({
  toast,
  durationSeconds,
  onDismiss,
}: {
  toast: IncomingToast;
  durationSeconds: number;
  onDismiss: () => void;
}) {
  const durationMs = Math.max(1000, durationSeconds * 1000);
  const [remainingMs, setRemainingMs] = useState(durationMs);
  const [paused, setPaused] = useState(false);

  useEffect(() => {
    setRemainingMs(durationMs);
    setPaused(false);
  }, [durationMs, toast.id]);

  useEffect(() => {
    if (paused) return;
    const timer = window.setInterval(() => {
      setRemainingMs((current) => {
        const next = current - 100;
        if (next <= 0) {
          window.clearInterval(timer);
          onDismiss();
          return 0;
        }
        return next;
      });
    }, 100);
    return () => window.clearInterval(timer);
  }, [durationMs, onDismiss, paused, toast.id]);

  const progress = Math.max(0, Math.min(100, (remainingMs / durationMs) * 100));
  return (
    <div
      className="incoming-message-toast"
      role="status"
      onMouseEnter={() => setPaused(true)}
      onMouseLeave={() => setPaused(false)}
    >
      <div className="incoming-message-toast-header">
        <strong>{toast.callsign}</strong>
        <span>RX</span>
      </div>
      <p>{toast.text}</p>
      <div className="incoming-message-toast-progress" aria-hidden="true">
        <span style={{ width: `${progress}%` }} />
      </div>
    </div>
  );
}

function HelpDrawer({
  open,
  topicId,
  onClose,
}: {
  open: boolean;
  topicId: string;
  onClose: () => void;
}) {
  const { language, t } = useLanguage();
  const [catalog, setCatalog] = useState<HelpCatalog>();
  const [activeTopicId, setActiveTopicId] = useState(topicId);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => setActiveTopicId(topicId), [topicId, open]);
  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    setLoading(true);
    setError("");
    void api<HelpCatalog>(`/api/help?lang=${language}`)
      .then((result) => {
        if (!cancelled) setCatalog(result);
      })
      .catch((reason) => {
        if (!cancelled) setError(errorMessage(reason));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [language, open]);
  useEffect(() => {
    if (!open) return;
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [onClose, open]);

  if (!open) return null;
  const available = catalog?.topics.map((topic) => topic.id) ?? [];
  const topic = catalog?.topics.find(
    (candidate) => candidate.id === resolveHelpTopicId(activeTopicId, available),
  );
  return (
    <div
      className="help-backdrop"
      role="presentation"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <aside
        className="help-drawer"
        role="dialog"
        aria-modal="true"
        aria-labelledby="help-drawer-title"
        onMouseDown={(event) => event.stopPropagation()}
      >
        <header className="help-drawer-header">
          <div>
            <span className="panel-eyebrow">JS8Link</span>
            <h2 id="help-drawer-title">{topic?.title ?? t("Help")}</h2>
          </div>
          <Button className="modal-close" aria-label={t("Sluiten")} onClick={onClose}>
            <X size={18} aria-hidden="true" />
          </Button>
        </header>
        <div className="help-drawer-body">
          {loading && <p className="muted">{t("Help laden…")}</p>}
          {error && (
            <div className="error">
              {t("Help niet beschikbaar")}: {error}
            </div>
          )}
          {!loading && !error && topic && (
            <>
              <p className="help-summary">{topic.summary}</p>
              {topic.sections.map((section) => (
                <section className="help-section" key={section.heading}>
                  <h3>{section.heading}</h3>
                  <p>{section.body}</p>
                </section>
              ))}
              {topic.steps.length > 0 && (
                <section className="help-section">
                  <h3>{t("Stappen")}</h3>
                  <ol>
                    {topic.steps.map((step) => (
                      <li key={step}>{step}</li>
                    ))}
                  </ol>
                </section>
              )}
              {topic.troubleshooting.length > 0 && (
                <section className="help-section">
                  <h3>{t("Problemen oplossen")}</h3>
                  <ul>
                    {topic.troubleshooting.map((item) => (
                      <li key={item}>{item}</li>
                    ))}
                  </ul>
                </section>
              )}
              {topic.references.length > 0 && (
                <section className="help-section">
                  <h3>{t("Referenties")}</h3>
                  <ul className="help-links">
                    {topic.references.map((reference) => (
                      <li key={reference.href}>
                        <a href={reference.href} target="_blank" rel="noreferrer">
                          {reference.label}
                        </a>
                      </li>
                    ))}
                  </ul>
                </section>
              )}
              {topic.related.length > 0 && catalog && (
                <section className="help-section">
                  <h3>{t("Gerelateerde onderwerpen")}</h3>
                  <div className="help-related">
                    {topic.related.map((related) => {
                      const relatedTopic = catalog.topics.find(
                        (candidate) => candidate.id === related,
                      );
                      return relatedTopic ? (
                        <Button
                          key={related}
                          className="secondary"
                          onClick={() => setActiveTopicId(related)}
                        >
                          {relatedTopic.title}
                        </Button>
                      ) : null;
                    })}
                  </div>
                </section>
              )}
            </>
          )}
        </div>
      </aside>
    </div>
  );
}

function escapeHtml(value: unknown): string {
  return String(value ?? "—").replace(
    /[&<>"]/g,
    (character) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[character] ?? character,
  );
}

function SetupWizard({ onDone }: { onDone: () => void }) {
  const steps = ["Welkom", "JS8Call", "Applicatie", "Afronden"];
  const [step, setStep] = useState(0);
  const [host, setHost] = useState("127.0.0.1");
  const [port, setPort] = useState("2442");
  const [error, setError] = useState("");
  const [testing, setTesting] = useState(false);
  const [version, setVersion] = useState("");
  const [authEnabled, setAuthEnabled] = useState(false);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [saving, setSaving] = useState(false);
  async function test() {
    setTesting(true);
    setError("");
    try {
      const result = await api<{ version: string }>("/api/setup/test-connection", {
        method: "POST",
        body: JSON.stringify({ host, port: Number(port) }),
      });
      setVersion(result.version);
    } catch (e) {
      setError(String(e));
    } finally {
      setTesting(false);
    }
  }
  async function save() {
    setSaving(true);
    setError("");
    try {
      await api("/api/setup/complete", {
        method: "POST",
        body: JSON.stringify({
          host,
          port: Number(port),
          auth_enabled: authEnabled,
          username,
          password,
        }),
      });
      onDone();
    } catch (e) {
      setError(String(e));
    } finally {
      setSaving(false);
    }
  }
  function next() {
    setError("");
    if (step === 1 && !version) {
      setError("Test eerst de verbinding met JS8Call.");
      return;
    }
    if (step === 2 && authEnabled && (!username || !password)) {
      setError("Vul een gebruikersnaam en wachtwoord in, of schakel de applicatielogin uit.");
      return;
    }
    setStep((current) => Math.min(current + 1, steps.length - 1));
  }
  return (
    <main className="shell setup-shell">
      <div className="topbar">
        <div className="brand">JS8Link</div>
      </div>
      <div className="wizard">
        <div className="wizard-progress" aria-label="Installatiestappen">
          {steps.map((label, index) => (
            <div className={`wizard-step ${index <= step ? "active" : ""}`} key={label}>
              <span className="wizard-step-number">{index + 1}</span>
              <span>{label}</span>
            </div>
          ))}
        </div>
        <Card>
          {step === 0 && (
            <div className="wizard-panel">
              <span className="eyebrow">Eerste configuratie</span>
              <h1>Welkom bij JS8Link</h1>
              <p className="lead">
                We lopen samen een paar korte stappen door om JS8Link met JS8Call-improved te
                verbinden.
              </p>
              <div className="info-box">
                <strong>Wat gaan we instellen?</strong>
                <span>
                  De verbinding met de JS8Call API en, indien gewenst, een login voor deze
                  webapplicatie.
                </span>
              </div>
              <p className="muted">
                JS8Call-improved moet actief zijn en de API moet ingeschakeld zijn voordat we de
                verbinding kunnen testen.
              </p>
            </div>
          )}
          {step === 1 && (
            <div className="wizard-panel">
              <span className="eyebrow">Stap 1 van 3</span>
              <h1>Verbind met JS8Call</h1>
              <p className="muted">Vul hier de host en TCP-poort van de JS8Call API in.</p>
              <div className="stack">
                <Label>
                  Host
                  <Input value={host} onChange={(e) => setHost(e.target.value)} />
                </Label>
                <Label>
                  TCP-poort
                  <Input type="number" value={port} onChange={(e) => setPort(e.target.value)} />
                </Label>
                <div className="row">
                  <Button onClick={test} disabled={testing}>
                    {testing ? "Testen…" : "Verbinding testen"}
                  </Button>
                  {version && (
                    <span className="status">
                      <span className="dot ok" />
                      JS8Call API {version} gevonden
                    </span>
                  )}
                </div>
              </div>
            </div>
          )}
          {step === 2 && (
            <div className="wizard-panel">
              <span className="eyebrow">Stap 2 van 3</span>
              <h1>Beveilig JS8Link</h1>
              <p className="muted">
                Dit gaat uitsluitend over toegang tot de JS8Link-webapplicatie, niet over JS8Call.
              </p>
              <div className="switch-row">
                <Switch checked={authEnabled} onCheckedChange={setAuthEnabled} />
                <span>Applicatielogin inschakelen</span>
              </div>
              <span className="muted">
                Met één gebruikersaccount voorkom je dat anderen op je netwerk JS8Link kunnen
                bedienen.
              </span>
              {authEnabled && (
                <div className="stack wizard-fields">
                  <Label>
                    Gebruikersnaam
                    <Input value={username} onChange={(e) => setUsername(e.target.value)} />
                  </Label>
                  <Label>
                    Wachtwoord
                    <Input
                      type="password"
                      value={password}
                      onChange={(e) => setPassword(e.target.value)}
                    />
                  </Label>
                </div>
              )}
            </div>
          )}
          {step === 3 && (
            <div className="wizard-panel">
              <span className="eyebrow">Stap 3 van 3</span>
              <h1>Klaar om te starten</h1>
              <p className="muted">Controleer de instellingen voordat JS8Link ze opslaat.</p>
              <div className="summary">
                <div>
                  <span className="muted">JS8Call API</span>
                  <strong>
                    {host}:{port}
                  </strong>
                </div>
                <div>
                  <span className="muted">API-versie</span>
                  <strong>{version || "Getest"}</strong>
                </div>
                <div>
                  <span className="muted">Applicatielogin</span>
                  <strong>{authEnabled ? `Ingeschakeld (${username})` : "Uitgeschakeld"}</strong>
                </div>
              </div>
            </div>
          )}
          {error && <div className="error wizard-error">{error}</div>}
          <div className="wizard-actions">
            {step > 0 ? (
              <Button
                className="secondary"
                onClick={() => {
                  setError("");
                  setStep((current) => current - 1);
                }}
              >
                Terug
              </Button>
            ) : (
              <span />
            )}
            {step < 3 ? (
              <Button onClick={next}>{step === 0 ? "Configuratie starten" : "Volgende"}</Button>
            ) : (
              <Button onClick={save} disabled={saving}>
                {saving ? "Opslaan…" : "Configuratie opslaan"}
              </Button>
            )}
          </div>
        </Card>
      </div>
    </main>
  );
}

function Login({ onDone }: { onDone: () => void }) {
  const { t } = useLanguage();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  async function submit() {
    try {
      await api("/api/auth/login", {
        method: "POST",
        body: JSON.stringify({ username, password }),
      });
      onDone();
    } catch (e) {
      setError(String(e));
    }
  }
  return (
    <main className="shell login-shell">
      <div className="topbar">
        <div className="brand">JS8Link</div>
      </div>
      <Card className="login-card">
        <span className="panel-eyebrow">{t("Secure station access")}</span>
        <h2>{t("Inloggen")}</h2>
        <p className="muted">{t("Sign in to open the JS8Link station console.")}</p>
        <div className="stack">
          <Label>
            {t("Gebruikersnaam")}
            <Input value={username} onChange={(e) => setUsername(e.target.value)} />
          </Label>
          <Label>
            {t("Wachtwoord")}
            <Input type="password" value={password} onChange={(e) => setPassword(e.target.value)} />
          </Label>
          {error && (
            <div className="error" role="alert">
              {error}
            </div>
          )}
          <Button onClick={submit}>{t("Inloggen")}</Button>
        </div>
      </Card>
    </main>
  );
}

type MenuItem = "chat" | "messages" | "monitor" | "settings";

type MonitorMessage = {
  id: number;
  sender: string;
  sender_source?: "api" | "parsed" | "offset_inferred";
  recipient?: string;
  text: string;
  type: string;
  command?: string;
  grid?: string;
  snr?: number;
  offset?: number;
  mode?: string;
  band?: string;
  is_heartbeat: boolean;
  received_at: string;
  kind?: string;
  direction?: "rx" | "tx";
};
type MonitorStation = {
  id: number;
  callsign: string;
  grid?: string;
  latitude?: number;
  longitude?: number;
  country?: string;
  location_source?: string;
  last_snr?: number;
  last_offset?: number;
  last_mode?: string;
  message_count: number;
  last_seen: string;
};
type BandActivityMessage = {
  id: number;
  callsign?: string;
  sender_source?: "api" | "parsed" | "offset_inferred";
  text: string;
  snr?: number;
  offset?: number;
  mode?: string;
  band?: string;
  received_at: string;
  kind?: string;
  direction?: "rx" | "tx";
};
type BandActivityGroup = {
  offset: number | null;
  messages: BandActivityMessage[];
  count: number;
};
type LastHeardStation = {
  callsign: string;
  grid?: string;
  heard_seconds_ago: number;
  last_snr?: number;
  last_offset?: number;
  last_mode?: string;
  last_tdrift?: number;
  distance_km?: number;
  last_seen: string;
  band?: string | null;
  direction?: "rx" | "tx";
};
type MonitorLink = {
  id: number;
  source: string;
  target: string;
  source_latitude?: number;
  source_longitude?: number;
  target_latitude?: number;
  target_longitude?: number;
  snr_at_source?: number;
  snr_at_target?: number;
  observations_at_source: number;
  observations_at_target: number;
  bidirectional: boolean;
  snr_forward?: number;
  snr_reverse?: number;
  forward_observations: number;
  reverse_observations: number;
  observation_count: number;
  distance_km?: number;
  label: string;
  last_seen: string;
};

type MonitorInspectorLink = {
  source: string;
  target: string;
  source_callsigns?: string[];
  target_callsigns?: string[];
  snr_at_source?: number;
  snr_at_target?: number;
  observations_at_source?: number;
  observations_at_target?: number;
  snr_forward?: number;
  snr_reverse?: number;
  forward_observations?: number;
  reverse_observations?: number;
  distance_km?: number;
  connections?: MonitorInspectorConnection[];
};

type MonitorInspectorConnection = {
  source: string;
  target: string;
  snr_at_source?: number;
  snr_at_target?: number;
  snr_forward?: number;
  snr_reverse?: number;
  distance_km?: number;
};

function MonitorStationDetails({
  station,
  links,
}: {
  station: MonitorInspectorStation;
  links: MonitorLink[];
}) {
  const { t } = useLanguage();
  const { formatDateTime } = useTimeDisplay();
  const stationsHeardByThisStation = links.flatMap((connection) => {
    if (connection.source !== station.callsign || connection.snr_at_source == null) return [];
    return [{ callsign: connection.target, snr: connection.snr_at_source }];
  });
  const stationsReceivingThisStation = links.flatMap((connection) => {
    if (connection.target !== station.callsign || connection.snr_at_target == null) return [];
    return [{ callsign: connection.source, snr: connection.snr_at_target }];
  });
  return (
    <>
      <section className="monitor-inspector-section">
        <h3>{t("Station")}</h3>
        <dl className="monitor-inspector-data-list">
          <div>
            <dt>{t("Grid")}</dt>
            <dd>{station.grid || "—"}</dd>
          </div>
          <div>
            <dt>{t("Country")}</dt>
            <dd>{station.country || "—"}</dd>
          </div>
          <div>
            <dt>{t("Distance")}</dt>
            <dd>{station.distance_km != null ? `${station.distance_km} km` : "—"}</dd>
          </div>
        </dl>
      </section>
      <section className="monitor-inspector-section">
        <h3>{t("Signal")}</h3>
        <dl className="monitor-inspector-data-list">
          <div>
            <dt>{t("SNR")}</dt>
            <dd>{station.last_snr != null ? `${station.last_snr} dB` : "—"}</dd>
          </div>
          <div>
            <dt>{t("Offset")}</dt>
            <dd>{station.last_offset != null ? `${station.last_offset} Hz` : "—"}</dd>
          </div>
          <div>
            <dt>{t("Mode")}</dt>
            <dd>{station.last_mode || "—"}</dd>
          </div>
          <div>
            <dt>{t("Last heard")}</dt>
            <dd>{station.last_seen ? formatDateTime(station.last_seen) : "—"}</dd>
          </div>
        </dl>
      </section>
      <section className="monitor-inspector-section">
        <h3>{t("Stations heard by this station")}</h3>
        <div className="monitor-station-relations">
          {stationsHeardByThisStation.length > 0 ? (
            stationsHeardByThisStation.map((relation) => (
              <div className="monitor-station-relation" key={`heard-${relation.callsign}`}>
                <strong>{relation.callsign}</strong>
                <span>
                  {t("SNR at receiver")}: {relation.snr} dB
                </span>
              </div>
            ))
          ) : (
            <span className="monitor-relation-empty">{t("No known stations")}</span>
          )}
        </div>
      </section>
      <section className="monitor-inspector-section">
        <h3>{t("Stations receiving this station")}</h3>
        <div className="monitor-station-relations">
          {stationsReceivingThisStation.length > 0 ? (
            stationsReceivingThisStation.map((relation) => (
              <div className="monitor-station-relation" key={`received-by-${relation.callsign}`}>
                <strong>{relation.callsign}</strong>
                <span>
                  {t("SNR at receiver")}: {relation.snr} dB
                </span>
              </div>
            ))
          ) : (
            <span className="monitor-relation-empty">{t("No known stations")}</span>
          )}
        </div>
      </section>
      <section className="monitor-inspector-section monitor-inspector-status">
        <h3>{t("Activity")}</h3>
        <span className={station.direction === "tx" ? "tx-badge" : "rx-badge"}>
          {station.direction === "tx" ? t("TX") : t("RX")}
        </span>
      </section>
    </>
  );
}

function HighlightedText({ text, query }: { text: string; query: string }) {
  const needle = query.trim();
  if (!needle) return <>{text}</>;

  const lowerText = text.toLocaleLowerCase();
  const lowerNeedle = needle.toLocaleLowerCase();
  const parts: React.ReactNode[] = [];
  let cursor = 0;
  let matchIndex = lowerText.indexOf(lowerNeedle, cursor);
  while (matchIndex >= 0) {
    if (matchIndex > cursor) parts.push(text.slice(cursor, matchIndex));
    parts.push(
      <mark key={`${matchIndex}-${needle}`}>
        {text.slice(matchIndex, matchIndex + needle.length)}
      </mark>,
    );
    cursor = matchIndex + needle.length;
    matchIndex = lowerText.indexOf(lowerNeedle, cursor);
  }
  if (cursor === 0) return <>{text}</>;
  if (cursor < text.length) parts.push(text.slice(cursor));
  return <>{parts}</>;
}

function solarGeometry(date: Date) {
  const dayOfYear =
    Math.floor(
      (Date.UTC(date.getUTCFullYear(), date.getUTCMonth(), date.getUTCDate()) -
        Date.UTC(date.getUTCFullYear(), 0, 0)) /
        86400000,
    ) || 1;
  const utcHours = date.getUTCHours() + date.getUTCMinutes() / 60 + date.getUTCSeconds() / 3600;
  const gamma = (2 * Math.PI * (dayOfYear - 1 + (utcHours - 12) / 24)) / 365;
  const declination =
    0.006918 -
    0.399912 * Math.cos(gamma) +
    0.070257 * Math.sin(gamma) -
    0.006758 * Math.cos(2 * gamma) +
    0.000907 * Math.sin(2 * gamma) -
    0.002697 * Math.cos(3 * gamma) +
    0.00148 * Math.sin(3 * gamma);
  const equationOfTime =
    229.18 *
    (0.000075 +
      0.001868 * Math.cos(gamma) -
      0.032077 * Math.sin(gamma) -
      0.014615 * Math.cos(2 * gamma) -
      0.040849 * Math.sin(2 * gamma));
  const subsolarLongitude = (((12 - (utcHours + equationOfTime / 60)) * 15 + 540) % 360) - 180;
  return { declination, subsolarLongitude };
}

function greylineGeoJson(date: Date) {
  const { declination, subsolarLongitude } = solarGeometry(date);
  const coordinates: [number, number][] = [];
  for (let longitude = -180; longitude <= 180; longitude += 1) {
    const hourAngle = ((longitude - subsolarLongitude) * Math.PI) / 180;
    const latitude =
      (Math.atan2(-Math.cos(hourAngle) * Math.cos(declination), Math.sin(declination)) * 180) /
      Math.PI;
    coordinates.push([longitude, latitude]);
  }
  return {
    type: "FeatureCollection" as const,
    features: [
      {
        type: "Feature" as const,
        properties: {},
        geometry: { type: "LineString" as const, coordinates },
      },
    ],
  };
}

/** Full-hemisphere polygon covering the night side of the greyline. */
function nightShadeGeoJson(date: Date) {
  const { declination, subsolarLongitude } = solarGeometry(date);
  const nightPole = declination > 0 ? -90 : 90;
  const ring: [number, number][] = [];
  for (let lon = -180; lon <= 180; lon += 1) {
    const ha = ((lon - subsolarLongitude) * Math.PI) / 180;
    const lat =
      (Math.atan2(-Math.cos(ha) * Math.cos(declination), Math.sin(declination)) * 180) / Math.PI;
    ring.push([lon, lat]);
  }
  ring.push([180, nightPole], [-180, nightPole], [-180, ring[0]![1]]);
  return {
    type: "FeatureCollection" as const,
    features: [
      {
        type: "Feature" as const,
        properties: {},
        geometry: { type: "Polygon" as const, coordinates: [ring] },
      },
    ],
  };
}

/** A band polygon from the greyline to *offsetDegrees* into the day side. */
function twilightBand(date: Date, offsetDegrees: number) {
  const { declination, subsolarLongitude } = solarGeometry(date);
  // poleSign points toward the night pole.  To go into the DAY side we
  // flip the sign: dayward = -(poleSign).
  const poleSign = declination > 0 ? -1 : 1;
  const daySign = -poleSign;
  const ring: [number, number][] = [];
  const shifted: [number, number][] = [];
  for (let lon = -180; lon <= 180; lon += 1) {
    const ha = ((lon - subsolarLongitude) * Math.PI) / 180;
    const lat =
      (Math.atan2(-Math.cos(ha) * Math.cos(declination), Math.sin(declination)) * 180) / Math.PI;
    ring.push([lon, lat]);
    shifted.push([lon, Math.max(-90, Math.min(90, lat + daySign * offsetDegrees))]);
  }
  const poly: [number, number][] = [...ring, ...shifted.reverse()];
  poly.push(poly[0]!);
  return {
    type: "FeatureCollection" as const,
    features: [
      {
        type: "Feature" as const,
        properties: {},
        geometry: { type: "Polygon" as const, coordinates: [poly] },
      },
    ],
  };
}

function MonitorMap({
  stations,
  links,
  centerLatitude,
  centerLongitude,
  zoom,
  popupsEnabled,
  greylineEnabled,
  bidirectionalOnly,
  clusterStations,
  localCallsign,
  onStationInspect,
  onClusterInspect,
  onLinkInspect,
}: {
  stations: MonitorStation[];
  links: MonitorLink[];
  centerLatitude: number;
  centerLongitude: number;
  zoom: number;
  popupsEnabled: boolean;
  greylineEnabled: boolean;
  bidirectionalOnly: boolean;
  clusterStations: boolean;
  localCallsign?: string | null;
  onStationInspect?: (callsign: string) => void;
  onClusterInspect?: (callsigns: string[]) => void;
  onLinkInspect?: (link: MonitorInspectorLink) => void;
}) {
  const { t } = useLanguage();
  const [globe, setGlobe] = useState(false);
  const [mapError, setMapError] = useState("");
  const mapElement = useRef<HTMLDivElement>(null);
  const mapInstance = useRef<MapInstance | null>(null);
  const hoverPopup = useRef<maplibregl.Popup | null>(null);
  const refreshStationMarkersRef = useRef<(() => void) | null>(null);
  const refreshVisibleLinksRef = useRef<(() => Promise<void>) | null>(null);
  const clusterSettingRef = useRef<boolean>(clusterStations);
  const stationMarkers = useRef<maplibregl.Marker[]>([]);
  const stationsRef = useRef(stations);
  const viewportSaveTimer = useRef<number | null>(null);
  const visibleLinksTimer = useRef<number | null>(null);
  const visibleLinksRequestId = useRef(0);
  const [map, setMap] = useState<MapInstance | null>(null);
  useEffect(() => {
    stationsRef.current = stations;
  }, [stations]);
  useEffect(() => {
    if (!mapElement.current || mapInstance.current) return;
    if (!window.WebGL2RenderingContext) {
      setMapError(t("WebGL2 is required for the interactive map."));
      return;
    }
    const instance = new maplibregl.Map({
      container: mapElement.current,
      style: {
        version: 8,
        sources: {
          osm: {
            type: "raster",
            tiles: ["https://tile.openstreetmap.org/{z}/{x}/{y}.png"],
            tileSize: 256,
            attribution: "© OpenStreetMap contributors",
          },
          greyline: {
            type: "geojson",
            data: greylineGeoJson(new Date()),
          },
          nightshade: {
            type: "geojson",
            data: nightShadeGeoJson(new Date()),
          },
          dusk: {
            type: "geojson",
            data: twilightBand(new Date(), 10),
          },
        },
        layers: [
          { id: "osm", type: "raster", source: "osm" },
          {
            id: "nightshade",
            type: "fill",
            source: "nightshade",
            paint: {
              "fill-color": "#0a1428",
              "fill-opacity": 0.22,
              "fill-antialias": true,
            },
          },
          {
            id: "dusk",
            type: "fill",
            source: "dusk",
            paint: {
              "fill-color": "#0a1428",
              "fill-opacity": 0.08,
              "fill-antialias": true,
            },
          },
          {
            id: "greyline",
            type: "line",
            source: "greyline",
            paint: {
              "line-color": "#f59e0b",
              "line-width": 1.5,
              "line-opacity": 0.7,
              "line-dasharray": [1.5, 1.5],
            },
          },
        ],
      },
      center: [5, 52],
      zoom: 3,
      attributionControl: {},
    });
    instance.addControl(new maplibregl.NavigationControl(), "top-right");
    instance.on("error", () => setMapError(t("Map unavailable")));
    const persistViewport = () => {
      if (viewportSaveTimer.current !== null) {
        window.clearTimeout(viewportSaveTimer.current);
      }
      viewportSaveTimer.current = window.setTimeout(() => {
        const center = instance.getCenter();
        void api("/api/preferences", {
          method: "PATCH",
          body: JSON.stringify({
            monitor_map_center_latitude: center.lat,
            monitor_map_center_longitude: center.lng,
            monitor_map_zoom: instance.getZoom(),
          }),
        }).catch(() => undefined);
        viewportSaveTimer.current = null;
      }, 350);
    };
    instance.on("moveend", persistViewport);
    instance.on("zoomend", persistViewport);
    const scheduleVisibleLinks = () => {
      if (visibleLinksTimer.current !== null) {
        window.clearTimeout(visibleLinksTimer.current);
      }
      visibleLinksTimer.current = window.setTimeout(() => {
        visibleLinksTimer.current = null;
        void refreshVisibleLinksRef.current?.();
      }, 80);
    };
    instance.on("moveend", scheduleVisibleLinks);
    instance.on("zoomend", scheduleVisibleLinks);
    mapInstance.current = instance;
    setMap(instance);
    return () => {
      if (viewportSaveTimer.current !== null) {
        window.clearTimeout(viewportSaveTimer.current);
      }
      if (visibleLinksTimer.current !== null) {
        window.clearTimeout(visibleLinksTimer.current);
      }
      mapInstance.current = null;
      refreshStationMarkersRef.current = null;
      refreshVisibleLinksRef.current = null;
      instance.remove();
    };
  }, [t]);
  useEffect(() => {
    if (!map) return;
    const updateGreyline = () => {
      const now = new Date();
      (map.getSource("greyline") as GeoJSONSource | undefined)?.setData(greylineGeoJson(now));
      (map.getSource("nightshade") as GeoJSONSource | undefined)?.setData(nightShadeGeoJson(now));
      (map.getSource("dusk") as GeoJSONSource | undefined)?.setData(twilightBand(now, 10));
      const visible = greylineEnabled ? "visible" : "none";
      for (const layer of ["greyline", "nightshade", "dusk"]) {
        if (map.getLayer(layer)) map.setLayoutProperty(layer, "visibility", visible);
      }
    };
    updateGreyline();
    const timer = window.setInterval(updateGreyline, 60_000);
    return () => window.clearInterval(timer);
  }, [greylineEnabled, map]);
  useEffect(() => {
    if (!map) return;
    const current = map.getCenter();
    if (
      Math.abs(current.lat - centerLatitude) > 0.000001 ||
      Math.abs(current.lng - centerLongitude) > 0.000001 ||
      Math.abs(map.getZoom() - zoom) > 0.000001
    ) {
      map.jumpTo({ center: [centerLongitude, centerLatitude], zoom });
    }
  }, [centerLatitude, centerLongitude, map, zoom]);
  useEffect(() => {
    if (!map) return;
    const applyProjection = () => {
      try {
        map.setProjection({ type: globe ? "globe" : "mercator" });
      } catch {
        setMapError(t("Map unavailable"));
      }
    };
    if (map.isStyleLoaded()) {
      applyProjection();
    } else {
      map.once("load", applyProjection);
      return () => {
        map.off("load", applyProjection);
      };
    }
  }, [globe, map, t]);
  useEffect(() => {
    if (!map) return;
    const update = () => {
      const locatedStations = stations.filter(
        (station) =>
          typeof station.latitude === "number" &&
          Number.isFinite(station.latitude) &&
          typeof station.longitude === "number" &&
          Number.isFinite(station.longitude),
      );
      const normalizedLocalCallsign = localCallsign?.trim().toUpperCase();
      const localLocatedStations = locatedStations.filter(
        (station) => station.callsign.toUpperCase() === normalizedLocalCallsign,
      );
      const remoteLocatedStations = locatedStations.filter(
        (station) => station.callsign.toUpperCase() !== normalizedLocalCallsign,
      );
      const displayCoordinates = new Map<string, [number, number]>();
      const stationsByLocation = new Map<string, MonitorStation[]>();
      localLocatedStations.forEach((station) => {
        displayCoordinates.set(station.callsign, [station.longitude!, station.latitude!]);
      });
      remoteLocatedStations.forEach((station) => {
        const locationKey = `${station.longitude!.toFixed(6)},${station.latitude!.toFixed(6)}`;
        const colocated = stationsByLocation.get(locationKey) ?? [];
        colocated.push(station);
        stationsByLocation.set(locationKey, colocated);
      });
      const spiderLegFeatures: Array<{
        type: "Feature";
        geometry: { type: "LineString"; coordinates: [[number, number], [number, number]] };
        properties: { callsign: string };
      }> = [];
      const spiderCenterFeatures: Array<{
        type: "Feature";
        geometry: { type: "Point"; coordinates: [number, number] };
        properties: { station_count: number };
      }> = [];
      stationsByLocation.forEach((colocated) => {
        const center: [number, number] = [colocated[0].longitude!, colocated[0].latitude!];
        if (colocated.length > 1) {
          spiderCenterFeatures.push({
            type: "Feature",
            geometry: { type: "Point", coordinates: center },
            properties: { station_count: colocated.length },
          });
        }
        colocated
          .sort((left, right) => left.callsign.localeCompare(right.callsign))
          .forEach((station, index) => {
            if (colocated.length === 1) {
              displayCoordinates.set(station.callsign, [station.longitude!, station.latitude!]);
              return;
            }
            // Prefix-derived locations often put several stations on exactly the
            // same coordinate. Fan them out around that shared position.
            const angle = (2 * Math.PI * index) / colocated.length;
            const radius = colocated.length === 2 ? 0.00016 : 0.0003;
            const longitudeScale = Math.max(Math.cos((station.latitude! * Math.PI) / 180), 0.2);
            const displayCoordinate: [number, number] = [
              station.longitude! + (Math.cos(angle) * radius) / longitudeScale,
              station.latitude! + Math.sin(angle) * radius,
            ];
            displayCoordinates.set(station.callsign, displayCoordinate);
            spiderLegFeatures.push({
              type: "Feature",
              geometry: { type: "LineString", coordinates: [center, displayCoordinate] },
              properties: { callsign: station.callsign },
            });
          });
      });
      const stationFeatures = remoteLocatedStations.map((station) => ({
        type: "Feature" as const,
        geometry: {
          type: "Point" as const,
          coordinates: displayCoordinates.get(station.callsign)!,
        },
        properties: {
          callsign: station.callsign,
          grid: station.grid ?? "",
          snr: station.last_snr ?? "",
          offset: station.last_offset ?? "",
          mode: station.last_mode ?? "",
          country: station.country ?? "",
          location_source: station.location_source ?? "",
        },
      }));
      const localStationFeatures = localLocatedStations.map((station) => ({
        type: "Feature" as const,
        geometry: {
          type: "Point" as const,
          coordinates: displayCoordinates.get(station.callsign)!,
        },
        properties: {
          callsign: station.callsign,
          grid: station.grid ?? "",
          snr: station.last_snr ?? "",
          offset: station.last_offset ?? "",
          mode: station.last_mode ?? "",
          country: station.country ?? "",
          location_source: station.location_source ?? "",
        },
      }));
      const linkFeatures = links
        .filter(
          (link) =>
            typeof link.source_latitude === "number" &&
            Number.isFinite(link.source_latitude) &&
            typeof link.source_longitude === "number" &&
            Number.isFinite(link.source_longitude) &&
            typeof link.target_latitude === "number" &&
            Number.isFinite(link.target_latitude) &&
            typeof link.target_longitude === "number" &&
            Number.isFinite(link.target_longitude) &&
            (!bidirectionalOnly || link.bidirectional),
        )
        .flatMap((link) => {
          const source = displayCoordinates.get(link.source) ?? [
            link.source_longitude!,
            link.source_latitude!,
          ];
          const target = displayCoordinates.get(link.target) ?? [
            link.target_longitude!,
            link.target_latitude!,
          ];
          const midpoint: [number, number] = [
            (source[0] + target[0]) / 2,
            (source[1] + target[1]) / 2,
          ];
          const properties = {
            source: link.source,
            target: link.target,
            snr_at_source: link.snr_at_source ?? "—",
            snr_at_target: link.snr_at_target ?? "—",
            observations_at_source: link.observations_at_source,
            observations_at_target: link.observations_at_target,
            bidirectional: link.bidirectional,
            // Legacy aliases retained in popup payloads for older consumers.
            snr_forward: link.snr_forward ?? "—",
            snr_reverse: link.snr_reverse ?? "—",
            forward_observations: link.forward_observations,
            reverse_observations: link.reverse_observations,
            distance: link.distance_km ?? "—",
          };
          return [
            {
              type: "Feature" as const,
              geometry: { type: "LineString" as const, coordinates: [source, midpoint] },
              properties: {
                ...properties,
                direction: "forward",
                snr: link.snr_at_source ?? null,
                has_snr: typeof link.snr_at_source === "number",
              },
            },
            {
              type: "Feature" as const,
              geometry: { type: "LineString" as const, coordinates: [target, midpoint] },
              properties: {
                ...properties,
                direction: "reverse",
                snr: link.snr_at_target ?? null,
                has_snr: typeof link.snr_at_target === "number",
              },
            },
          ];
        });
      const stationSource = map.getSource("stations") as GeoJSONSource | undefined;
      const localStationSource = map.getSource("local-station") as GeoJSONSource | undefined;
      const linkSource = map.getSource("links") as GeoJSONSource | undefined;
      const spiderLegSource = map.getSource("station-spider-legs") as GeoJSONSource | undefined;
      const spiderCenterSource = map.getSource("station-spider-centers") as
        GeoJSONSource | undefined;
      const stationData = { type: "FeatureCollection" as const, features: stationFeatures };
      const localStationData = {
        type: "FeatureCollection" as const,
        features: localStationFeatures,
      };
      const linkData = { type: "FeatureCollection" as const, features: linkFeatures };
      const spiderLegData = {
        type: "FeatureCollection" as const,
        features: spiderLegFeatures,
      };
      const spiderCenterData = {
        type: "FeatureCollection" as const,
        features: spiderCenterFeatures,
      };
      const refreshVisibleLinks = async () => {
        const requestId = ++visibleLinksRequestId.current;
        const currentStationSource = map.getSource("stations") as GeoJSONSource | undefined;
        const currentLinkSource = map.getSource("links") as GeoJSONSource | undefined;
        if (!currentStationSource || !currentLinkSource) return;

        type VisibleNode = {
          id: string;
          label: string;
          coordinates: [number, number];
          callsigns: string[];
        };
        type ConnectionDetail = {
          source: string;
          target: string;
          snr_at_source?: number;
          snr_at_target?: number;
          snr_forward?: number;
          snr_reverse?: number;
          distance_km?: number;
        };
        type ConnectionGroup = {
          source: VisibleNode;
          target: VisibleNode;
          sourceSnr: number[];
          targetSnr: number[];
          sourceObservations: number;
          targetObservations: number;
          connections: ConnectionDetail[];
        };

        const nodeByCallsign = new Map<string, VisibleNode>();
        locatedStations.forEach((station) => {
          const coordinates = displayCoordinates.get(station.callsign);
          if (!coordinates) return;
          nodeByCallsign.set(station.callsign, {
            id: `station:${station.callsign}`,
            label: station.callsign,
            coordinates,
            callsigns: [station.callsign],
          });
        });

        const renderedClusters = map
          .queryRenderedFeatures({ layers: ["station-clusters"] })
          .filter(
            (feature, index, features) =>
              features.findIndex(
                (candidate) => candidate.properties?.cluster_id === feature.properties?.cluster_id,
              ) === index,
          );
        await Promise.all(
          renderedClusters.map(async (feature) => {
            if (feature.geometry.type !== "Point") return;
            const clusterId = Number(feature.properties?.cluster_id);
            const pointCount = Number(feature.properties?.point_count ?? 0);
            if (!Number.isFinite(clusterId) || pointCount < 1) return;
            const leaves = await currentStationSource.getClusterLeaves(clusterId, pointCount, 0);
            const callsigns = [
              ...new Set(
                leaves.map((leaf) => String(leaf.properties?.callsign ?? "")).filter(Boolean),
              ),
            ].sort();
            if (!callsigns.length) return;
            const node: VisibleNode = {
              id: `cluster:${clusterId}`,
              label: `${callsigns.length} ${t("Stations").toLowerCase()}`,
              coordinates: feature.geometry.coordinates as [number, number],
              callsigns,
            };
            callsigns.forEach((callsign) => nodeByCallsign.set(callsign, node));
          }),
        );
        if (requestId !== visibleLinksRequestId.current) return;

        const groups = new Map<string, ConnectionGroup>();
        links.forEach((link) => {
          // Keep the interactive source in sync with the rendered source.
          // Otherwise a later viewport refresh reintroduced one-way links
          // after the bidirectional-only filter had removed them.
          if (bidirectionalOnly && !link.bidirectional) return;
          const sourceNode = nodeByCallsign.get(link.source);
          const targetNode = nodeByCallsign.get(link.target);
          if (!sourceNode || !targetNode || sourceNode.id === targetNode.id) return;
          const sourceFirst = sourceNode.id.localeCompare(targetNode.id) < 0;
          const first = sourceFirst ? sourceNode : targetNode;
          const second = sourceFirst ? targetNode : sourceNode;
          const key = `${first.id}|${second.id}`;
          const group = groups.get(key) ?? {
            source: first,
            target: second,
            sourceSnr: [],
            targetSnr: [],
            sourceObservations: 0,
            targetObservations: 0,
            connections: [],
          };
          if (sourceFirst) {
            if (typeof link.snr_at_source === "number") group.sourceSnr.push(link.snr_at_source);
            if (typeof link.snr_at_target === "number") group.targetSnr.push(link.snr_at_target);
            group.sourceObservations += link.observations_at_source;
            group.targetObservations += link.observations_at_target;
          } else {
            if (typeof link.snr_at_target === "number") group.sourceSnr.push(link.snr_at_target);
            if (typeof link.snr_at_source === "number") group.targetSnr.push(link.snr_at_source);
            group.sourceObservations += link.observations_at_target;
            group.targetObservations += link.observations_at_source;
          }
          group.connections.push({
            source: link.source,
            target: link.target,
            snr_at_source: link.snr_at_source,
            snr_at_target: link.snr_at_target,
            snr_forward: link.snr_forward,
            snr_reverse: link.snr_reverse,
            distance_km: link.distance_km,
          });
          groups.set(key, group);
        });

        const groupedFeatures = [...groups.values()].flatMap((group) => {
          const midpoint: [number, number] = [
            (group.source.coordinates[0] + group.target.coordinates[0]) / 2,
            (group.source.coordinates[1] + group.target.coordinates[1]) / 2,
          ];
          const sourceSnr = averageSnr(group.sourceSnr);
          const targetSnr = averageSnr(group.targetSnr);
          const properties = {
            source: group.source.label,
            target: group.target.label,
            source_callsigns: group.source.callsigns.join(", "),
            target_callsigns: group.target.callsigns.join(", "),
            snr_at_source: sourceSnr ?? "—",
            snr_at_target: targetSnr ?? "—",
            observations_at_source: group.sourceObservations,
            observations_at_target: group.targetObservations,
            snr_forward: sourceSnr ?? "—",
            snr_reverse: targetSnr ?? "—",
            forward_observations: group.sourceObservations,
            reverse_observations: group.targetObservations,
            distance: "—",
            connection_count: group.connections.length,
            connections_json: JSON.stringify(group.connections),
          };
          return [
            {
              type: "Feature" as const,
              geometry: {
                type: "LineString" as const,
                coordinates: [group.source.coordinates, midpoint],
              },
              properties: {
                ...properties,
                direction: "forward",
                snr: sourceSnr,
                has_snr: sourceSnr !== null,
              },
            },
            {
              type: "Feature" as const,
              geometry: {
                type: "LineString" as const,
                coordinates: [group.target.coordinates, midpoint],
              },
              properties: {
                ...properties,
                direction: "reverse",
                snr: targetSnr,
                has_snr: targetSnr !== null,
              },
            },
          ];
        });
        currentLinkSource.setData({
          type: "FeatureCollection",
          features: groupedFeatures,
        });
      };
      refreshVisibleLinksRef.current = refreshVisibleLinks;
      if (stationSource) stationSource.setData(stationData);
      if (localStationSource) localStationSource.setData(localStationData);
      if (linkSource) linkSource.setData(linkData);
      if (spiderLegSource) spiderLegSource.setData(spiderLegData);
      if (spiderCenterSource) spiderCenterSource.setData(spiderCenterData);
      // Rebuild station source when cluster setting changes
      const clusterChanged =
        stationSource !== undefined &&
        clusterSettingRef.current !== undefined &&
        clusterSettingRef.current !== clusterStations;
      if (clusterChanged) {
        map.removeLayer("station-unclustered");
        map.removeLayer("station-clusters");
        map.removeSource("stations");
      }
      const effectiveStationSource = clusterChanged ? undefined : stationSource;
      clusterSettingRef.current = clusterStations;
      if (stationSource && refreshStationMarkersRef.current) {
        map.once("idle", () => refreshStationMarkersRef.current?.());
      }
      if (!spiderLegSource) {
        map.addSource("station-spider-legs", { type: "geojson", data: spiderLegData });
        map.addLayer({
          id: "station-spider-legs",
          type: "line",
          source: "station-spider-legs",
          minzoom: 18.5,
          paint: {
            "line-color": "#64748b",
            "line-width": 1.5,
            "line-opacity": 0.9,
          },
        });
      }
      if (!localStationSource) {
        map.addSource("local-station", { type: "geojson", data: localStationData });
        map.addLayer({
          id: "local-station",
          type: "circle",
          source: "local-station",
          paint: {
            "circle-radius": 7,
            "circle-color": "#f59e0b",
            "circle-stroke-color": "#fff",
            "circle-stroke-width": 2,
          },
        });
      }
      if (!spiderCenterSource) {
        map.addSource("station-spider-centers", { type: "geojson", data: spiderCenterData });
        map.addLayer({
          id: "station-spider-centers",
          type: "circle",
          source: "station-spider-centers",
          minzoom: 18.5,
          paint: {
            "circle-radius": 4,
            "circle-color": "#e2e8f0",
            "circle-stroke-color": "#475569",
            "circle-stroke-width": 1.5,
          },
        });
      }
      if (!effectiveStationSource) {
        map.addSource("stations", {
          type: "geojson",
          data: stationData,
          cluster: clusterStations,
          clusterRadius: 50,
          // Keep nearby stations grouped until the user has zoomed in far
          // enough to inspect them individually.
          clusterMaxZoom: 17,
        });
        map.addLayer({
          id: "station-clusters",
          type: "circle",
          source: "stations",
          paint: {
            "circle-radius": ["step", ["get", "point_count"], 18, 10, 22, 50, 28],
            "circle-color": [
              "step",
              ["get", "point_count"],
              "#2563eb",
              10,
              "#7c3aed",
              50,
              "#be185d",
            ],
            "circle-stroke-color": "#fff",
            "circle-stroke-width": 2,
          },
        });
        map.addLayer({
          id: "station-unclustered",
          type: "circle",
          source: "stations",
          filter: ["!", ["has", "point_count"]],
          paint: {
            "circle-radius": 6,
            "circle-color": "#60a5fa",
            "circle-stroke-color": "#fff",
            "circle-stroke-width": 1,
          },
        });
        const inspectLinkProperties = (properties: Record<string, unknown>) => {
          const optionalNumber = (value: unknown) => {
            const numeric = Number(value);
            return Number.isFinite(numeric) ? numeric : undefined;
          };
          let connections: MonitorInspectorConnection[] = [];
          try {
            const parsed = JSON.parse(String(properties.connections_json ?? "[]"));
            if (Array.isArray(parsed)) connections = parsed;
          } catch {
            connections = [];
          }
          onLinkInspect?.({
            source: String(properties.source || "—"),
            target: String(properties.target || "—"),
            source_callsigns: String(properties.source_callsigns || "")
              .split(",")
              .map((callsign) => callsign.trim())
              .filter(Boolean),
            target_callsigns: String(properties.target_callsigns || "")
              .split(",")
              .map((callsign) => callsign.trim())
              .filter(Boolean),
            snr_at_source: optionalNumber(properties.snr_at_source),
            snr_at_target: optionalNumber(properties.snr_at_target),
            observations_at_source: optionalNumber(properties.observations_at_source),
            observations_at_target: optionalNumber(properties.observations_at_target),
            snr_forward: optionalNumber(properties.snr_forward),
            snr_reverse: optionalNumber(properties.snr_reverse),
            forward_observations: optionalNumber(properties.forward_observations),
            reverse_observations: optionalNumber(properties.reverse_observations),
            distance_km: optionalNumber(properties.distance),
            connections,
          });
        };
        const underlyingConnectionsHtml = (properties: Record<string, unknown>) => {
          try {
            const sourceCallsigns = String(properties.source_callsigns ?? "")
              .split(",")
              .map((callsign) => callsign.trim())
              .filter(Boolean);
            const targetCallsigns = String(properties.target_callsigns ?? "")
              .split(",")
              .map((callsign) => callsign.trim())
              .filter(Boolean);
            if (sourceCallsigns.length < 2 && targetCallsigns.length < 2) return "";
            const connections = JSON.parse(
              String(properties.connections_json ?? "[]"),
            ) as MonitorInspectorConnection[];
            if (!connections.length) return "";
            return `<br><strong>${t("Underlying connections")}</strong><br>${connections
              .map(
                (connection) =>
                  `${escapeHtml(connection.source)} ↔ ${escapeHtml(connection.target)} · SNR ${escapeHtml(connection.snr_at_source)} / ${escapeHtml(connection.snr_at_target)} dB · ${escapeHtml(connection.distance_km)} km`,
              )
              .join("<br>")}`;
          } catch {
            return "";
          }
        };
        map.on("click", "station-links", (event) => {
          const clicked = event.features?.[0];
          const properties = clicked?.properties;
          if (!properties) return;
          inspectLinkProperties(properties);
          if (!popupsEnabled) return;
          const escape = (value: unknown) =>
            String(value ?? "—").replace(
              /[&<>"]/g,
              (character) =>
                ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[character] ?? character,
            );
          new maplibregl.Popup()
            .setLngLat(event.lngLat)
            .setHTML(
              `<strong>${escape(properties.direction === "forward" ? `${properties.source} → ${properties.target}` : `${properties.target} → ${properties.source}`)}</strong><br>${t("Received by")} ${escape(properties.source)}: ${escape(properties.snr_at_source)} dB<br>${t("Received by")} ${escape(properties.target)}: ${escape(properties.snr_at_target)} dB<br>${escape(properties.distance)} km${underlyingConnectionsHtml(properties)}`,
            )
            .addTo(map);
        });
        map.on("mouseenter", "station-links", () => {
          map.getCanvas().style.cursor = "pointer";
        });
        map.on("mouseleave", "station-links", () => {
          map.getCanvas().style.cursor = "";
        });
        map.on("click", "station-links-uncertain", (event) => {
          const clicked = event.features?.[0];
          const properties = clicked?.properties;
          if (!properties) return;
          inspectLinkProperties(properties);
          if (!popupsEnabled) return;
          const direction =
            properties.direction === "forward"
              ? `${properties.source} → ${properties.target}`
              : `${properties.target} → ${properties.source}`;
          const escape = (value: unknown) =>
            String(value ?? "—").replace(
              /[&<>"]/g,
              (character) =>
                ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[character] ?? character,
            );
          new maplibregl.Popup()
            .setLngLat(event.lngLat)
            .setHTML(
              `<strong>${escape(direction)}</strong><br>${t("No reception confirmation known for this direction")}`,
            )
            .addTo(map);
        });
        map.on("mouseenter", "station-links-uncertain", () => {
          map.getCanvas().style.cursor = "pointer";
        });
        map.on("mouseleave", "station-links-uncertain", () => {
          map.getCanvas().style.cursor = "";
        });
        const showLinkHover = (
          event: maplibregl.MapMouseEvent & { features?: maplibregl.MapGeoJSONFeature[] },
        ) => {
          const properties = event.features?.[0]?.properties;
          if (!properties) return;
          inspectLinkProperties(properties);
          if (!popupsEnabled) return;
          const direction =
            properties.direction === "forward"
              ? `${properties.source} → ${properties.target}`
              : `${properties.target} → ${properties.source}`;
          const connectionDetails = underlyingConnectionsHtml(properties);
          hoverPopup.current?.remove();
          hoverPopup.current = new maplibregl.Popup({
            closeButton: false,
            closeOnClick: false,
            offset: 10,
          })
            .setLngLat(event.lngLat)
            .setHTML(
              `<strong>${escapeHtml(direction)}</strong><br>${t("Received by")} ${escapeHtml(String(properties.source))}: ${escapeHtml(properties.snr_at_source)} dB (${escapeHtml(properties.observations_at_source)} ${t("observations")})<br>${t("Received by")} ${escapeHtml(String(properties.target))}: ${escapeHtml(properties.snr_at_target)} dB (${escapeHtml(properties.observations_at_target)} ${t("observations")})${connectionDetails}`,
            )
            .addTo(map);
        };
        for (const layerId of ["station-links", "station-links-uncertain"]) {
          map.on("mouseenter", layerId, showLinkHover);
          map.on("mouseleave", layerId, () => hoverPopup.current?.remove());
        }
        const refreshStationMarkers = () => {
          const renderedFeatures = map.queryRenderedFeatures({
            layers: ["station-clusters", "station-unclustered", "local-station"],
          });
          // MapLibre may return the same rendered feature from more than one
          // tile (or world copy). Create at most one HTML marker per station or
          // cluster, otherwise a callsign can appear twice on the map.
          const visibleFeatures = [
            ...new Map(
              renderedFeatures.map((feature) => {
                const properties = feature.properties ?? {};
                const identity =
                  properties.cluster_id !== undefined
                    ? `cluster:${properties.cluster_id}`
                    : `station:${properties.callsign}`;
                return [identity, feature] as const;
              }),
            ).values(),
          ];
          const stationLocationCounts = new Map<string, number>();
          visibleFeatures.forEach((feature) => {
            if (feature.properties?.cluster_id !== undefined) return;
            if (feature.geometry.type !== "Point") return;
            const [longitude, latitude] = feature.geometry.coordinates as [number, number];
            const key = `${longitude.toFixed(6)},${latitude.toFixed(6)}`;
            stationLocationCounts.set(key, (stationLocationCounts.get(key) ?? 0) + 1);
          });
          const stationLocationIndexes = new Map<string, number>();
          stationMarkers.current.forEach((marker) => marker.remove());
          stationMarkers.current = visibleFeatures.flatMap((visibleFeature) => {
            if (visibleFeature.geometry.type !== "Point") return [];
            const coordinates = visibleFeature.geometry.coordinates as [number, number];
            const properties = visibleFeature.properties ?? {};
            const element = document.createElement("div");
            const clusterId = properties.cluster_id;
            if (clusterId !== undefined) {
              element.className = "cluster-marker";
              element.textContent = String(
                properties.point_count_abbreviated ?? properties.point_count,
              );
              element.title = t("Inspect grouped stations");
              element.addEventListener("click", () => {
                const source = map.getSource("stations") as GeoJSONSource;
                void source
                  .getClusterLeaves(Number(clusterId), Number(properties.point_count ?? 1000), 0)
                  .then((leaves) => {
                    const callsigns = [
                      ...new Set(
                        leaves
                          .map((leaf) => String(leaf.properties?.callsign ?? ""))
                          .filter(Boolean),
                      ),
                    ].sort();
                    onClusterInspect?.(callsigns);
                  });
              });
              let clusterHovered = false;
              element.addEventListener("mouseenter", () => {
                if (!popupsEnabled) return;
                clusterHovered = true;
                const source = map.getSource("stations") as GeoJSONSource;
                void source
                  .getClusterLeaves(Number(clusterId), Number(properties.point_count ?? 1000), 0)
                  .then((leaves) => {
                    if (!clusterHovered) return;
                    const callsigns = [
                      ...new Set(
                        leaves
                          .map((leaf) => String(leaf.properties?.callsign ?? ""))
                          .filter(Boolean),
                      ),
                    ].sort();
                    const stationDetails = callsigns
                      .map((callsign) => {
                        const station = stationsRef.current.find(
                          (candidate) => candidate.callsign === callsign,
                        );
                        return `<strong>${escapeHtml(callsign)}</strong>${station?.grid ? ` · ${escapeHtml(station.grid)}` : ""}${station?.last_snr !== undefined ? ` · ${escapeHtml(station.last_snr)} dB` : ""}${station?.last_mode ? ` · ${escapeHtml(station.last_mode)}` : ""}`;
                      })
                      .join("<br>");
                    hoverPopup.current?.remove();
                    hoverPopup.current = new maplibregl.Popup({
                      closeButton: false,
                      closeOnClick: false,
                      offset: 18,
                    })
                      .setLngLat(coordinates)
                      .setHTML(
                        `<strong>${t("Grouped stations")} (${callsigns.length})</strong><br>${stationDetails}`,
                      )
                      .addTo(map);
                  });
              });
              element.addEventListener("mouseleave", () => {
                clusterHovered = false;
                hoverPopup.current?.remove();
              });
            } else {
              const station = stationsRef.current.find(
                (candidate) => candidate.callsign === properties.callsign,
              );
              if (!station) return [];
              element.className = "station-marker";
              element.textContent = station.callsign;
              const locationKey = `${coordinates[0].toFixed(6)},${coordinates[1].toFixed(6)}`;
              const locationCount = stationLocationCounts.get(locationKey) ?? 1;
              const locationIndex = stationLocationIndexes.get(locationKey) ?? 0;
              stationLocationIndexes.set(locationKey, locationIndex + 1);
              element.title =
                [
                  station.grid,
                  station.last_snr !== undefined ? `${station.last_snr} dB` : "",
                  station.last_offset !== undefined ? `${station.last_offset} Hz` : "",
                  station.last_mode,
                  station.country,
                  station.location_source,
                ]
                  .filter(Boolean)
                  .join(" · ") || station.callsign;
              const showStationPopup = () => {
                onStationInspect?.(station.callsign);
                if (!popupsEnabled) return;
                hoverPopup.current?.remove();
                hoverPopup.current = new maplibregl.Popup({
                  closeButton: false,
                  closeOnClick: false,
                  offset: 12,
                })
                  .setLngLat(coordinates)
                  .setHTML(
                    `<strong>${escapeHtml(station.callsign)}</strong><br>${t("Grid")}: ${escapeHtml(station.grid)}<br>${t("Country")}: ${escapeHtml(station.country)}<br>${t("Last SNR")}: ${escapeHtml(station.last_snr !== undefined ? `${station.last_snr} dB` : "—")}<br>${t("Offset")}: ${escapeHtml(station.last_offset !== undefined ? `${station.last_offset} Hz` : "—")}<br>${t("Mode")}: ${escapeHtml(station.last_mode)}`,
                  )
                  .addTo(map);
              };
              element.addEventListener("mouseenter", showStationPopup);
              element.addEventListener("click", () => onStationInspect?.(station.callsign));
              element.addEventListener("mouseleave", () => hoverPopup.current?.remove());
              const angle = (2 * Math.PI * locationIndex) / locationCount;
              const radius = locationCount === 2 ? 24 : 30;
              const offset: [number, number] =
                locationCount > 1
                  ? [Math.round(Math.cos(angle) * radius), Math.round(Math.sin(angle) * radius)]
                  : [0, 0];
              return [new maplibregl.Marker({ element, offset }).setLngLat(coordinates).addTo(map)];
            }
            return [new maplibregl.Marker({ element }).setLngLat(coordinates).addTo(map)];
          });
        };
        refreshStationMarkersRef.current = refreshStationMarkers;
        map.on("idle", refreshStationMarkers);
        map.on("moveend", refreshStationMarkers);
        map.on("zoomend", refreshStationMarkers);
        refreshStationMarkers();
      }
      if (!linkSource) {
        map.addSource("links", { type: "geojson", data: linkData });
        map.addLayer({
          id: "station-links-uncertain-halo",
          type: "line",
          source: "links",
          filter: ["==", ["get", "has_snr"], false],
          layout: {
            "line-cap": "round",
            "line-join": "round",
          },
          paint: {
            "line-color": "#0f172a",
            "line-width": 3.5,
            "line-opacity": 0.45,
          },
        });
        map.addLayer({
          id: "station-links-uncertain",
          type: "line",
          source: "links",
          filter: ["==", ["get", "has_snr"], false],
          layout: {
            "line-cap": "round",
            "line-join": "round",
          },
          paint: {
            "line-color": "#cbd5e1",
            "line-width": 1.75,
            "line-opacity": 0.72,
            "line-dasharray": [1.2, 1.5],
          },
        });
        map.addLayer({
          id: "station-links",
          type: "line",
          source: "links",
          filter: ["==", ["get", "has_snr"], true],
          paint: {
            "line-color": [
              "interpolate",
              ["linear"],
              ["get", "snr"],
              -20,
              "#ef4444",
              -7,
              "#f59e0b",
              0,
              "#22c55e",
              10,
              "#38bdf8",
            ],
            "line-width": 3,
            "line-opacity": 0.75,
          },
        });
        // Bidirectional links: both sides have known SNR → mutual reception.
        // Render these more prominently with a subtle glow and wider line.
        map.addLayer({
          id: "station-links-bidirectional",
          type: "line",
          source: "links",
          filter: ["all", ["==", ["get", "has_snr"], true], ["==", ["get", "bidirectional"], true]],
          paint: {
            "line-color": [
              "interpolate",
              ["linear"],
              ["get", "snr"],
              -20,
              "#ef4444",
              -7,
              "#f59e0b",
              0,
              "#22c55e",
              10,
              "#38bdf8",
            ],
            "line-width": 5,
            "line-opacity": 0.35,
            "line-blur": 3,
          },
        });
      }
      map.once("idle", () => void refreshVisibleLinksRef.current?.());
    };
    if (map.isStyleLoaded()) update();
    else map.once("load", update);
  }, [
    links,
    localCallsign,
    map,
    bidirectionalOnly,
    clusterStations,
    onLinkInspect,
    onStationInspect,
    onClusterInspect,
    popupsEnabled,
    stations,
    t,
  ]);
  return (
    <div className="map-wrapper">
      <div className="map-toolbar">
        <div className="tabs-list">
          <button
            className={`tabs-trigger ${!globe ? "active" : ""}`}
            onClick={() => setGlobe(false)}
          >
            {t("Flat map")}
          </button>
          <button
            className={`tabs-trigger ${globe ? "active" : ""}`}
            onClick={() => setGlobe(true)}
          >
            {t("Globe")}
          </button>
        </div>
      </div>
      {mapError ? (
        <div className="map-error">{mapError}</div>
      ) : (
        <div className="map" ref={mapElement} />
      )}
    </div>
  );
}

type MonitorInspectorStation = {
  callsign: string;
  grid?: string;
  country?: string;
  last_snr?: number;
  last_offset?: number;
  last_mode?: string;
  last_seen?: string;
  distance_km?: number;
  direction?: "rx" | "tx";
};

function MonitorStationInspector({
  station,
  stations,
  link,
  links = [],
  onClose,
  onFilterStation,
  filteredCallsign,
}: {
  station?: MonitorInspectorStation;
  stations?: MonitorInspectorStation[];
  link?: MonitorInspectorLink;
  links?: MonitorLink[];
  onClose: () => void;
  onFilterStation?: (callsign: string) => void;
  filteredCallsign?: string;
}) {
  const { t } = useLanguage();
  if (!station && !link && stations && stations.length > 0) {
    return (
      <aside className="monitor-station-inspector" aria-label={t("Stationinformatie")}>
        <div className="monitor-station-inspector-header">
          <div>
            <span className="panel-eyebrow">{t("Station inspector")}</span>
            <h2>{t("Grouped stations")}</h2>
            <p>
              {stations.length} {t("Stations").toLowerCase()}
            </p>
          </div>
          <button
            type="button"
            className="monitor-inspector-close"
            onClick={onClose}
            aria-label={t("Sluiten")}
          >
            <X size={15} aria-hidden="true" />
          </button>
        </div>
        {stations.map((groupedStation) => (
          <section className="monitor-inspector-station-card" key={groupedStation.callsign}>
            <div className="monitor-station-inspector-header">
              <div>
                <span className="panel-eyebrow">{t("Station")}</span>
                <h2>{groupedStation.callsign}</h2>
                <p>{groupedStation.country || t("Naam niet vastgelegd")}</p>
              </div>
              {onFilterStation && (
                <button
                  type="button"
                  className={`monitor-inspector-filter-icon ${filteredCallsign === groupedStation.callsign ? "active" : ""}`}
                  onClick={() => onFilterStation(groupedStation.callsign)}
                  aria-label={t("Filter op dit station")}
                  title={t("Filter op dit station")}
                >
                  <Filter size={15} aria-hidden="true" />
                </button>
              )}
            </div>
            <MonitorStationDetails station={groupedStation} links={links} />
          </section>
        ))}
      </aside>
    );
  }
  if (!station && !link) {
    return (
      <aside className="monitor-station-inspector empty" aria-label={t("Stationinformatie")}>
        <div className="monitor-station-inspector-header">
          <div>
            <span className="panel-eyebrow">{t("Station inspector")}</span>
            <h2>{t("No selection")}</h2>
            <p>{t("Select a station or connection on the map or in the table.")}</p>
          </div>
        </div>
      </aside>
    );
  }
  if (link) {
    const sourceStations = link.source_callsigns ?? [];
    const targetStations = link.target_callsigns ?? [];
    const groupedSource = sourceStations.length > 1;
    const groupedTarget = targetStations.length > 1;
    const groupedRelation = groupedSource || groupedTarget;
    const groupedStations = groupedSource ? sourceStations : targetStations;
    const actualStation = groupedSource ? link.target : groupedTarget ? link.source : undefined;
    const underlyingConnections = groupedRelation ? (link.connections ?? []) : [];
    const connectionHeading = groupedSource
      ? `${sourceStations.length} ${t("Stations").toLowerCase()} → ${link.target}`
      : groupedTarget
        ? `${link.source} → ${targetStations.length} ${t("Stations").toLowerCase()}`
        : `${link.source} ↔ ${link.target}`;
    return (
      <aside className="monitor-station-inspector" aria-label={t("Connection details")}>
        <div className="monitor-station-inspector-header">
          <div>
            <span className="panel-eyebrow">{t("Connection inspector")}</span>
            <h2>{connectionHeading}</h2>
            <p>{actualStation ? t("Individual station details") : t("Observed radio path")}</p>
          </div>
          <button
            type="button"
            className="monitor-inspector-close"
            onClick={onClose}
            aria-label={t("Sluiten")}
          >
            <X size={15} aria-hidden="true" />
          </button>
        </div>
        <section className="monitor-inspector-section">
          {underlyingConnections.length > 0 ? (
            <>
              <h3>{t("Underlying connections")}</h3>
              <div className="monitor-inspector-connection-list">
                {underlyingConnections.map((connection, index) => (
                  <div
                    className="monitor-inspector-connection-card"
                    key={`${connection.source}-${connection.target}-${index}`}
                  >
                    <h4>
                      {connection.source} ↔ {connection.target}
                    </h4>
                    <dl className="monitor-inspector-data-list">
                      <div>
                        <dt>
                          {t("Received by")} {connection.source}
                        </dt>
                        <dd>
                          {connection.snr_at_source != null
                            ? `${connection.snr_at_source} dB`
                            : "—"}
                        </dd>
                      </div>
                      <div>
                        <dt>
                          {t("Received by")} {connection.target}
                        </dt>
                        <dd>
                          {connection.snr_at_target != null
                            ? `${connection.snr_at_target} dB`
                            : "—"}
                        </dd>
                      </div>
                      <div>
                        <dt>{t("Distance")}</dt>
                        <dd>
                          {connection.distance_km != null ? `${connection.distance_km} km` : "—"}
                        </dd>
                      </div>
                    </dl>
                  </div>
                ))}
              </div>
            </>
          ) : actualStation && groupedStations.length > 0 ? (
            <>
              <h3>{t("Reception by station")}</h3>
              <div className="monitor-underlying-connections">
                {link.connections?.map((connection, index) => {
                  const callsign = groupedSource ? connection.source : connection.target;
                  const snr = groupedSource ? connection.snr_at_source : connection.snr_at_target;
                  return (
                    <div
                      className="monitor-underlying-connection monitor-reception-detail"
                      key={`${callsign}-${index}`}
                    >
                      <strong>{callsign}</strong>
                      <span>
                        {t("Received by")} {callsign}: {snr != null ? `${snr} dB` : "—"}
                      </span>
                    </div>
                  );
                })}
              </div>
            </>
          ) : (
            <>
              <h3>{t("Signal")}</h3>
              <dl className="monitor-inspector-data-list">
                <div>
                  <dt>
                    {t("Received by")} {link.source}
                  </dt>
                  <dd>{link.snr_at_source != null ? `${link.snr_at_source} dB` : "—"}</dd>
                </div>
                <div>
                  <dt>
                    {t("Received by")} {link.target}
                  </dt>
                  <dd>{link.snr_at_target != null ? `${link.snr_at_target} dB` : "—"}</dd>
                </div>
                <div>
                  <dt>{t("Distance")}</dt>
                  <dd>{link.distance_km != null ? `${link.distance_km} km` : "—"}</dd>
                </div>
              </dl>
            </>
          )}
        </section>
        <section className="monitor-inspector-section">
          <h3>{t("Observations")}</h3>
          <dl className="monitor-inspector-data-list">
            <div>
              <dt>
                {t("At")} {link.source}
              </dt>
              <dd>{link.observations_at_source ?? 0}</dd>
            </div>
            <div>
              <dt>
                {t("At")} {link.target}
              </dt>
              <dd>{link.observations_at_target ?? 0}</dd>
            </div>
          </dl>
        </section>
      </aside>
    );
  }
  if (!station) return null;
  return (
    <aside className="monitor-station-inspector" aria-label={t("Stationinformatie")}>
      <div className="monitor-station-inspector-header">
        <div>
          <span className="panel-eyebrow">{t("Station inspector")}</span>
          <h2>{station.callsign}</h2>
          <p>{station.country || t("Naam niet vastgelegd")}</p>
        </div>
        <div className="monitor-inspector-header-actions">
          {onFilterStation && (
            <button
              type="button"
              className={`monitor-inspector-filter-icon ${filteredCallsign === station.callsign ? "active" : ""}`}
              onClick={() => onFilterStation(station.callsign)}
              aria-label={
                filteredCallsign === station.callsign
                  ? t("Filter wissen")
                  : t("Filter op dit station")
              }
              title={
                filteredCallsign === station.callsign
                  ? t("Filter wissen")
                  : t("Filter op dit station")
              }
            >
              <Filter size={15} aria-hidden="true" />
            </button>
          )}
          <button
            type="button"
            className="monitor-inspector-close"
            onClick={onClose}
            aria-label={t("Sluiten")}
          >
            <X size={15} aria-hidden="true" />
          </button>
        </div>
      </div>
      <MonitorStationDetails station={station} links={links} />
    </aside>
  );
}

function MonitorPanel({
  onHistoryMinutesChange,
  localCallsign,
}: {
  onHistoryMinutesChange?: (minutes: number) => void;
  localCallsign?: string | null;
}) {
  const { t } = useLanguage();
  const { formatTime, formatDateTime } = useTimeDisplay();
  const [messages, setMessages] = useState<MonitorMessage[]>([]);
  const [bandActivity, setBandActivity] = useState<BandActivityGroup[]>([]);
  const [lastHeard, setLastHeard] = useState<LastHeardStation[]>([]);
  const [stations, setStations] = useState<MonitorStation[]>([]);
  const [links, setLinks] = useState<MonitorLink[]>([]);
  const [selectedBand, setSelectedBand] = useState("");
  const [sortKey, setSortKey] = useState<
    "sender" | "received_at" | "band" | "type" | "snr" | "offset" | "mode"
  >("received_at");
  const [sortDirection, setSortDirection] = useState<"asc" | "desc">("desc");
  const [historyMinutes, setHistoryMinutes] = useState(1440);
  const [currentTime, setCurrentTime] = useState(() => Date.now());
  const [mapHeight, setMapHeight] = useState(400);
  const [mapCenterLatitude, setMapCenterLatitude] = useState(52);
  const [mapCenterLongitude, setMapCenterLongitude] = useState(5);
  const [mapZoom, setMapZoom] = useState(3);
  const [mapPopups, setMapPopups] = useState(true);
  const [mapGreyline, setMapGreyline] = useState(true);
  const [mapBidirectionalOnly, setMapBidirectionalOnly] = useState(false);
  const [mapClusterStations, setMapClusterStations] = useState(true);
  const [monitorView, setMonitorView] = useState<"messages" | "activity" | "last_heard">(
    "messages",
  );
  const [selectedStationCallsign, setSelectedStationCallsign] = useState("");
  const [selectedStationCallsigns, setSelectedStationCallsigns] = useState<string[]>([]);
  const [filteredStationCallsign, setFilteredStationCallsign] = useState("");
  const [monitorSearchOpen, setMonitorSearchOpen] = useState(false);
  const [monitorSearch, setMonitorSearch] = useState("");
  const [selectedMonitorLink, setSelectedMonitorLink] = useState<MonitorInspectorLink>();
  const [dragging, setDragging] = useState(false);
  const historySaveTimer = useRef<number | null>(null);
  const [historyPreferenceError, setHistoryPreferenceError] = useState("");
  const monitorRequestId = useRef(0);
  const monitorLoadTimer = useRef<number | null>(null);
  async function savePreference(preference: Record<string, unknown>) {
    try {
      return await api<{ monitor_map_height?: number }>("/api/preferences", {
        method: "PATCH",
        body: JSON.stringify(preference),
      });
    } catch (reason) {
      setHistoryPreferenceError(errorMessage(reason));
      return undefined;
    }
  }
  const loadMonitor = useCallback(async () => {
    const requestId = ++monitorRequestId.current;
    const query = new URLSearchParams({ minutes: String(historyMinutes) });
    if (selectedBand) query.set("band", selectedBand);
    // Clear links immediately when filter params change so connections
    // outside the new time window don't flash on the map before the API
    // response arrives.  Stations are kept to avoid a blank map.
    setLinks([]);
    const [messageData, graph, activityData, lastHeardData] = await Promise.all([
      api<{ messages: MonitorMessage[] }>(`/api/monitor/messages?${query}`),
      api<{ stations: MonitorStation[]; links: MonitorLink[] }>(`/api/monitor/graph?${query}`),
      api<{ groups: BandActivityGroup[] }>(`/api/monitor/band-activity?${query}`).catch(() => ({
        groups: [],
      })),
      api<{ stations: LastHeardStation[] }>("/api/monitor/last-heard"),
    ]);
    // A slider change can start another request before this one completes.
    // Never let an older response replace the data for the current selection.
    if (requestId !== monitorRequestId.current) return;
    setMessages(
      messageData.messages.map((message) =>
        message.direction === "tx" && localCallsign
          ? { ...message, sender: localCallsign }
          : message,
      ),
    );
    setStations(graph.stations);
    setLinks(graph.links);
    setBandActivity(activityData.groups);
    setLastHeard(lastHeardData.stations);
  }, [historyMinutes, localCallsign, selectedBand]);
  const loadMonitorRef = useRef(loadMonitor);
  useEffect(() => {
    loadMonitorRef.current = loadMonitor;
  }, [loadMonitor]);
  const scheduleMonitorLoad = useCallback(() => {
    if (monitorLoadTimer.current !== null) {
      window.clearTimeout(monitorLoadTimer.current);
    }
    monitorLoadTimer.current = window.setTimeout(() => {
      monitorLoadTimer.current = null;
      void loadMonitorRef.current();
    }, 350);
  }, []);
  useEffect(() => {
    void api<{
      history_minutes: number;
      monitor_band: string | null;
      monitor_sort_key: typeof sortKey;
      monitor_sort_direction: "asc" | "desc";
      monitor_map_height: number;
      monitor_map_center_latitude: number;
      monitor_map_center_longitude: number;
      monitor_map_zoom: number;
      monitor_map_popups: boolean;
      monitor_map_greyline: boolean;
      monitor_map_bidirectional_only: boolean;
      monitor_map_cluster_stations: boolean;
      monitor_view: "messages" | "activity" | "last_heard";
    }>("/api/preferences")
      .then((preference) => {
        setHistoryMinutes(preference.history_minutes);
        onHistoryMinutesChange?.(preference.history_minutes);
        setSelectedBand(preference.monitor_band || "");
        setSortKey(preference.monitor_sort_key);
        setSortDirection(preference.monitor_sort_direction);
        setMapHeight(preference.monitor_map_height);
        setMapCenterLatitude(preference.monitor_map_center_latitude);
        setMapCenterLongitude(preference.monitor_map_center_longitude);
        setMapZoom(preference.monitor_map_zoom);
        setMapPopups(preference.monitor_map_popups);
        setMapGreyline(preference.monitor_map_greyline);
        setMapBidirectionalOnly(preference.monitor_map_bidirectional_only);
        setMapClusterStations(preference.monitor_map_cluster_stations);
        setMonitorView(preference.monitor_view);
      })
      .catch((reason) => setHistoryPreferenceError(errorMessage(reason)));
  }, [onHistoryMinutesChange]);
  useEffect(() => {
    scheduleMonitorLoad();
    const protocol = location.protocol === "https:" ? "wss" : "ws";
    const socket = new WebSocket(`${protocol}://${location.host}/api/events`);
    socket.onmessage = (event) => {
      try {
        const payload = JSON.parse(event.data) as {
          event?: string;
          data?: {
            id?: number;
            type?: string;
            sender?: string;
            text?: string;
            snr?: number;
            offset?: number;
            mode?: string;
            band?: string;
            received_at?: string;
            is_duplicate?: boolean;
            callsign?: string;
            to_callsign?: string;
            from_callsign?: string;
            command?: string;
            timestamp?: string;
          };
        };
        const eventName = payload.event?.toLowerCase() ?? "";

        if (eventName === "activity.received" && payload.data?.id && !payload.data.is_duplicate) {
          // Prepend the new message directly — no full reload needed.
          const newMsg: MonitorMessage = {
            id: payload.data.id,
            sender: payload.data.sender || "",
            sender_source: "parsed",
            text: payload.data.text || "",
            type: payload.data.type || "rx.activity",
            snr: payload.data.snr ?? undefined,
            offset: payload.data.offset ?? undefined,
            mode: payload.data.mode || "Normal",
            band: payload.data.band || "",
            is_heartbeat: false,
            received_at: payload.data.received_at || new Date().toISOString(),
            direction: "rx",
            recipient: payload.data.to_callsign || undefined,
          };
          setMessages((current) => [newMsg, ...current]);
          // Still schedule a reload for graph/activity/last-heard updates.
          return;
        }

        // Also handle TX frames directly.
        if (eventName === "radio.tx_frame" && payload.data) {
          const txMsg: MonitorMessage = {
            id: -(payload.data.id || Date.now()),
            sender: localCallsign || "TX",
            sender_source: "api",
            text: payload.data.text || "",
            type: "TX.FRAME",
            snr: undefined,
            offset: payload.data.offset ?? undefined,
            mode: payload.data.mode || "Normal",
            band: payload.data.band || "",
            is_heartbeat: false,
            received_at: new Date().toISOString(),
            direction: "tx",
          };
          setMessages((current) => [txMsg, ...current]);
          return;
        }

        const monitorEvents = new Set([
          "activity.received",
          "chat.message.received",
          "chat.message.sent",
          "radio.spot",
          "radio.tx_frame",
        ]);
        if (monitorEvents.has(eventName)) scheduleMonitorLoad();
      } catch {
        // Ignore malformed event envelopes.
      }
    };
    // Periodic full reload as fallback for graph/activity/last-heard/consistency.
    const fallbackTimer = window.setInterval(scheduleMonitorLoad, 30_000);
    return () => {
      socket.close();
      window.clearInterval(fallbackTimer);
    };
  }, [scheduleMonitorLoad, localCallsign]);
  useEffect(() => {
    scheduleMonitorLoad();
  }, [historyMinutes, selectedBand, scheduleMonitorLoad]);
  useEffect(
    () => () => {
      if (historySaveTimer.current) window.clearTimeout(historySaveTimer.current);
      if (monitorLoadTimer.current !== null) window.clearTimeout(monitorLoadTimer.current);
    },
    [],
  );
  useEffect(() => {
    const timer = window.setInterval(() => setCurrentTime(Date.now()), 60_000);
    return () => window.clearInterval(timer);
  }, []);
  const availableBands = [
    ...new Set(messages.map((message) => message.band).filter(Boolean)),
  ].sort() as string[];
  const historyLabel = historyMinutes < 60 ? `${historyMinutes} min` : `${historyMinutes / 60} uur`;
  const historyCutoff = currentTime - historyMinutes * 60_000;
  const visibleMessages = messages.filter(
    (message) =>
      (!selectedBand || message.band === selectedBand) &&
      (!filteredStationCallsign ||
        message.sender.toUpperCase() === filteredStationCallsign.toUpperCase()) &&
      (!monitorSearch.trim() ||
        message.sender.toLocaleLowerCase().includes(monitorSearch.trim().toLocaleLowerCase()) ||
        message.text.toLocaleLowerCase().includes(monitorSearch.trim().toLocaleLowerCase())) &&
      parseStoredUtc(message.received_at).getTime() >= historyCutoff,
  );
  const visibleCallsigns = new Set(visibleMessages.map((message) => message.sender));
  const visibleLastHeard = lastHeard.filter(
    (station) =>
      station.heard_seconds_ago <= historyMinutes * 60 &&
      (!selectedBand ||
        (station.direction === "tx"
          ? station.band === selectedBand
          : visibleCallsigns.has(station.callsign))) &&
      (!monitorSearch.trim() ||
        station.callsign.toLocaleLowerCase().includes(monitorSearch.trim().toLocaleLowerCase())),
  );
  const selectedMonitorStation = selectedStationCallsign
    ? (() => {
        const graphStation = stations.find(
          (station) => station.callsign === selectedStationCallsign,
        );
        const heardStation = lastHeard.find(
          (station) => station.callsign === selectedStationCallsign,
        );
        return graphStation || heardStation;
      })()
    : undefined;
  const selectedMonitorStations = selectedStationCallsigns
    .map((callsign) => stations.find((candidate) => candidate.callsign === callsign))
    .filter((candidate): candidate is MonitorStation => Boolean(candidate));
  const inspectStation = useCallback((callsign: string) => {
    setSelectedStationCallsign(callsign);
    setSelectedStationCallsigns([]);
    setSelectedMonitorLink(undefined);
  }, []);
  const inspectStationGroup = useCallback((callsigns: string[]) => {
    setSelectedStationCallsign("");
    setSelectedStationCallsigns(callsigns);
    setSelectedMonitorLink(undefined);
  }, []);
  const senderMatchesSelection = (callsign?: string | null) =>
    Boolean(
      callsign &&
      selectedStationCallsign &&
      callsign.toUpperCase() === selectedStationCallsign.toUpperCase(),
    );
  const inspectLink = useCallback((link: MonitorInspectorLink) => {
    setSelectedMonitorLink(link);
    setSelectedStationCallsign("");
    setSelectedStationCallsigns([]);
  }, []);
  const clearInspection = useCallback(() => {
    setSelectedStationCallsign("");
    setSelectedStationCallsigns([]);
    setSelectedMonitorLink(undefined);
  }, []);
  const toggleStationFilter = useCallback((callsign: string) => {
    setFilteredStationCallsign((current) =>
      current.toUpperCase() === callsign.toUpperCase() ? "" : callsign,
    );
  }, []);
  const filteredMapGraph = filterStationGraph(stations, links, filteredStationCallsign);
  const filteredBandActivity = bandActivity
    .map((group) => ({
      ...group,
      messages: filteredStationCallsign
        ? group.messages.filter(
            (message) => message.callsign?.toUpperCase() === filteredStationCallsign.toUpperCase(),
          )
        : group.messages,
    }))
    .map((group) => ({
      ...group,
      messages: monitorSearch.trim()
        ? group.messages.filter(
            (message) =>
              message.callsign
                ?.toLocaleLowerCase()
                .includes(monitorSearch.trim().toLocaleLowerCase()) ||
              message.text.toLocaleLowerCase().includes(monitorSearch.trim().toLocaleLowerCase()),
          )
        : group.messages,
    }))
    .filter((group) => group.messages.length > 0);
  const sortedMessages = [...visibleMessages].sort((left, right) => {
    const leftValue = left[sortKey] ?? "";
    const rightValue = right[sortKey] ?? "";
    const comparison =
      sortKey === "snr"
        ? Number(typeof leftValue === "number" ? leftValue : -999) -
          Number(typeof rightValue === "number" ? rightValue : -999)
        : String(leftValue).localeCompare(String(rightValue), undefined, {
            numeric: true,
            sensitivity: "base",
          });
    return sortDirection === "asc" ? comparison : -comparison;
  });
  function sortBy(nextKey: typeof sortKey) {
    const nextDirection =
      sortKey === nextKey
        ? sortDirection === "asc"
          ? "desc"
          : "asc"
        : nextKey === "received_at"
          ? "desc"
          : "asc";
    if (sortKey !== nextKey) {
      setSortKey(nextKey);
    }
    setSortDirection(nextDirection);
    void savePreference({ monitor_sort_key: nextKey, monitor_sort_direction: nextDirection });
  }
  function selectView(view: "messages" | "activity" | "last_heard") {
    setMonitorView(view);
    void savePreference({ monitor_view: view });
  }
  function formatAgo(seconds: number) {
    if (seconds < 60) return `${seconds}s`;
    if (seconds < 3600) return `${Math.floor(seconds / 60)}m`;
    return `${Math.floor(seconds / 3600)}h`;
  }
  function startResize(event: React.PointerEvent<HTMLDivElement>) {
    event.currentTarget.setPointerCapture(event.pointerId);
    setDragging(true);
    const startY = event.clientY;
    const startHeight = mapHeight;
    let finalHeight = startHeight;
    function move(pointerEvent: PointerEvent) {
      finalHeight = Math.round(
        Math.max(280, Math.min(900, startHeight + pointerEvent.clientY - startY)),
      );
      setMapHeight(finalHeight);
    }
    function stop() {
      setDragging(false);
      void savePreference({ monitor_map_height: finalHeight }).then((saved) => {
        if (saved?.monitor_map_height !== undefined) {
          setMapHeight(saved.monitor_map_height);
        }
      });
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", stop);
    }
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", stop);
  }
  return (
    <div className="monitor-layout wide">
      <div className="monitor-commandbar">
        <div className="monitor-command-title">
          <Activity size={18} aria-hidden="true" />
          <div>
            <span className="panel-eyebrow">{t("Spectrum workspace")}</span>
            <h1>{t("Band Monitor")}</h1>
          </div>
        </div>
        <div className="monitor-command-stats" aria-label={t("Monitor status")}>
          <div className="monitor-stat rx">
            <span>{t("Traffic items")}</span>
            <strong>{sortedMessages.length}</strong>
          </div>
          <div className="monitor-stat stations">
            <span>{t("Stations")}</span>
            <strong>{filteredMapGraph.stations.length}</strong>
          </div>
          <div className="monitor-stat links">
            <span>{t("Relations")}</span>
            <strong>{filteredMapGraph.links.length}</strong>
          </div>
        </div>
        <div className="monitor-toolbar">
          <Label>
            <span className="control-label">
              <SlidersHorizontal size={12} aria-hidden="true" /> {t("Band")}
            </span>
            <select
              className="select compact-select"
              value={selectedBand}
              onChange={(event) => {
                const nextBand = event.target.value;
                setSelectedBand(nextBand);
                void savePreference({ monitor_band: nextBand || null });
              }}
            >
              <option value="">{t("All bands")}</option>
              {availableBands.map((band) => (
                <option value={band} key={band}>
                  {band}
                </option>
              ))}
            </select>
          </Label>
          <Label className="history-control">
            <span className="control-label">
              <Clock3 size={12} aria-hidden="true" /> {t("History")}
              <strong>{historyLabel}</strong>
            </span>
            <input
              className="history-slider"
              type="range"
              min="15"
              max="1440"
              step="15"
              value={historyMinutes}
              onChange={(event) => {
                const nextValue = Number(event.target.value);
                setHistoryMinutes(nextValue);
                onHistoryMinutesChange?.(nextValue);
                if (historySaveTimer.current) window.clearTimeout(historySaveTimer.current);
                historySaveTimer.current = window.setTimeout(() => {
                  void savePreference({ history_minutes: nextValue });
                }, 300);
              }}
            />
          </Label>
        </div>
        {historyPreferenceError && <small className="error">{historyPreferenceError}</small>}
      </div>
      <div className="monitor-workspace-grid">
        <div className="monitor-primary-stack">
          <Card
            className="monitor-map-card"
            style={{ "--map-height": `${mapHeight}px` } as React.CSSProperties}
          >
            <div className="monitor-heading monitor-map-heading">
              <div className="panel-title-with-icon">
                <MapPin size={16} aria-hidden="true" />
                <div>
                  <span className="panel-eyebrow">{t("Propagation map")}</span>
                  <h2>{t("Stations map")}</h2>
                  <span className="muted">
                    {filteredMapGraph.stations.length} {t("Stations").toLowerCase()} ·{" "}
                    {filteredMapGraph.links.length} {t("Relations").toLowerCase()}
                  </span>
                </div>
              </div>
              <div className="map-signal-scale" aria-label={t("SNR color scale")}>
                <span className="signal-poor">-20</span>
                <span className="signal-fair">-7</span>
                <span className="signal-good">0</span>
                <span className="signal-strong">+10 dB</span>
              </div>
            </div>
            <MonitorMap
              stations={filteredMapGraph.stations}
              links={filteredMapGraph.links}
              centerLatitude={mapCenterLatitude}
              centerLongitude={mapCenterLongitude}
              zoom={mapZoom}
              popupsEnabled={mapPopups}
              greylineEnabled={mapGreyline}
              bidirectionalOnly={mapBidirectionalOnly}
              clusterStations={mapClusterStations}
              localCallsign={localCallsign}
              onStationInspect={inspectStation}
              onClusterInspect={inspectStationGroup}
              onLinkInspect={inspectLink}
            />
            <div className="map-legend">
              <span>
                <MapPin size={13} aria-hidden="true" /> {t("Stations")}
              </span>
              <span className="map-legend-snr">
                <Waypoints size={14} aria-hidden="true" /> SNR
              </span>
              <span className="map-legend-unknown-snr">
                <i aria-hidden="true" /> {t("Unknown reception SNR")}
              </span>
            </div>
          </Card>
          <div
            className={`monitor-resizer ${dragging ? "dragging" : ""}`}
            role="separator"
            aria-orientation="horizontal"
            aria-label={t("Resize monitor panels")}
            onPointerDown={startResize}
          >
            <span />
          </div>
          <Card className="monitor-messages">
            <div className="monitor-table-tabsbar">
              <Tabs
                value={monitorView}
                onValueChange={(value) =>
                  selectView(value as "messages" | "activity" | "last_heard")
                }
              >
                <TabsList>
                  <TabsTrigger
                    value="messages"
                    active={monitorView === "messages"}
                    onClick={() => selectView("messages")}
                  >
                    {t("Traffic")}
                  </TabsTrigger>
                  <TabsTrigger
                    value="activity"
                    active={monitorView === "activity"}
                    onClick={() => selectView("activity")}
                  >
                    {t("By offset")}
                  </TabsTrigger>
                  <TabsTrigger
                    value="last_heard"
                    active={monitorView === "last_heard"}
                    onClick={() => selectView("last_heard")}
                  >
                    {t("Last heard")}
                  </TabsTrigger>
                </TabsList>
              </Tabs>
              <div className="monitor-table-summary">
                <Activity size={13} aria-hidden="true" />
                <span>
                  {monitorView === "last_heard"
                    ? `${visibleLastHeard.length} ${t("Stations").toLowerCase()}`
                    : `${sortedMessages.length} ${t("Traffic items").toLowerCase()}`}
                </span>
                {filteredStationCallsign && (
                  <button
                    type="button"
                    className="monitor-filter-chip"
                    onClick={() => toggleStationFilter(filteredStationCallsign)}
                  >
                    {t("Station")}: {filteredStationCallsign} <X size={11} aria-hidden="true" />
                  </button>
                )}
                {monitorSearchOpen && (
                  <Input
                    className="monitor-search-input"
                    value={monitorSearch}
                    onChange={(event) => setMonitorSearch(event.target.value)}
                    placeholder={t("Zoek afzender of bericht…")}
                    aria-label={t("Zoek afzender of bericht…")}
                  />
                )}
                <button
                  type="button"
                  className={`monitor-search-toggle ${monitorSearchOpen || monitorSearch ? "active" : ""}`}
                  aria-label={t("Filter verkeer")}
                  aria-pressed={monitorSearchOpen}
                  title={t("Filter verkeer")}
                  onClick={() =>
                    setMonitorSearchOpen((open) => {
                      if (open) setMonitorSearch("");
                      return !open;
                    })
                  }
                >
                  <Search size={14} aria-hidden="true" />
                </button>
              </div>
            </div>
            {monitorView === "last_heard" ? (
              visibleLastHeard.length === 0 ? (
                <p className="muted">{t("No stations heard yet.")}</p>
              ) : (
                <div className="monitor-table-wrapper">
                  <table className="monitor-table">
                    <thead>
                      <tr>
                        <th>{t("Station")}</th>
                        <th>{t("Last heard")}</th>
                        <th className="snr-cell">{t("SNR")}</th>
                        <th>{t("Offset")}</th>
                        <th>{t("Mode")}</th>
                        <th>{t("Grid")}</th>
                        <th>{t("Distance")}</th>
                        <th>{t("Direction")}</th>
                      </tr>
                    </thead>
                    <tbody>
                      {visibleLastHeard.map((station) => (
                        <tr
                          className={`${station.direction === "tx" ? "tx-row" : ""} ${senderMatchesSelection(station.callsign) ? "sender-match selected-row" : ""}`}
                          key={station.callsign}
                          onClick={() => inspectStation(station.callsign)}
                        >
                          <td className="strong-cell">
                            <HighlightedText text={station.callsign} query={monitorSearch} />
                          </td>
                          <td>{formatAgo(station.heard_seconds_ago)}</td>
                          <td className="snr-cell">
                            {station.last_snr !== undefined ? `${station.last_snr} dB` : "—"}
                          </td>
                          <td>
                            {station.last_offset !== undefined ? `${station.last_offset} Hz` : "—"}
                          </td>
                          <td>{station.last_mode || "—"}</td>
                          <td>{station.grid || "—"}</td>
                          <td>{station.distance_km != null ? `${station.distance_km} km` : "—"}</td>
                          <td>
                            <span className={station.direction === "tx" ? "tx-badge" : "rx-badge"}>
                              {station.direction === "tx" ? t("TX") : t("RX")}
                            </span>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )
            ) : monitorView === "activity" ? (
              filteredBandActivity.length === 0 ? (
                <p className="muted">{t("No traffic on this offset yet.")}</p>
              ) : (
                <div className="monitor-table-wrapper monitor-offset-table-wrapper">
                  <table className="monitor-table monitor-offset-table">
                    <thead>
                      <tr>
                        <th>{t("Time")}</th>
                        <th>{t("Sender")}</th>
                        <th className="snr-cell">{t("SNR")}</th>
                        <th>{t("Mode")}</th>
                        <th>{t("Message")}</th>
                      </tr>
                    </thead>
                    <tbody>
                      {filteredBandActivity.flatMap((group) => {
                        const latestStation = group.messages.find((message) => message.callsign);
                        return [
                          <tr className="monitor-offset-row" key={`offset-${group.offset}`}>
                            <th colSpan={5} scope="rowgroup">
                              <span>
                                {t("Offset")}{" "}
                                {group.offset != null ? `${group.offset} Hz` : t("Unknown")}
                              </span>
                              <span className="muted">
                                · {t("Last heard")}: {latestStation?.callsign || t("Onbekend")} ·{" "}
                                {group.count} {t("Traffic items").toLowerCase()}
                              </span>
                            </th>
                          </tr>,
                          ...group.messages.map((message) => (
                            <tr
                              className={`${message.direction === "tx" ? "tx-row" : ""} ${senderMatchesSelection(message.callsign) ? "sender-match selected-row" : ""}`}
                              key={message.id}
                              onClick={() => message.callsign && inspectStation(message.callsign)}
                            >
                              <td className="nowrap">{formatTime(message.received_at)}</td>
                              <td
                                className={
                                  message.direction === "tx"
                                    ? "tx-sender strong-cell"
                                    : message.sender_source === "offset_inferred"
                                      ? "derived-sender strong-cell"
                                      : "strong-cell"
                                }
                                title={
                                  message.sender_source === "offset_inferred"
                                    ? t(
                                        "Sender inferred from the most recent station on this offset",
                                      )
                                    : undefined
                                }
                              >
                                <HighlightedText
                                  text={message.callsign || t("Onbekend")}
                                  query={monitorSearch}
                                />
                              </td>
                              <td className="snr-cell">
                                {message.snr !== undefined ? `${message.snr} dB` : "—"}
                              </td>
                              <td>{message.mode || "—"}</td>
                              <td className="message-cell">
                                <HighlightedText text={message.text || "—"} query={monitorSearch} />
                              </td>
                            </tr>
                          )),
                        ];
                      })}
                    </tbody>
                  </table>
                </div>
              )
            ) : sortedMessages.length === 0 ? (
              <p className="muted">{t("No band traffic yet.")}</p>
            ) : (
              <div className="monitor-table-wrapper">
                <table className="monitor-table">
                  <thead>
                    <tr>
                      {(
                        [
                          ["received_at", t("Time")],
                          ["sender", t("Sender")],
                          ["band", t("Band")],
                          ["type", t("Type")],
                          ["snr", t("SNR")],
                          ["offset", t("Offset")],
                          ["mode", t("Mode")],
                        ] as const
                      ).map(([key, label]) => (
                        <th
                          className={key === "snr" ? "snr-cell" : undefined}
                          key={key}
                          scope="col"
                          aria-sort={
                            sortKey === key
                              ? sortDirection === "asc"
                                ? "ascending"
                                : "descending"
                              : "none"
                          }
                        >
                          <button className="sort-header" onClick={() => sortBy(key)}>
                            {label}
                            {sortKey === key && (
                              <span className="sort-direction" aria-hidden="true">
                                {sortDirection === "asc" ? (
                                  <ArrowUp size={11} />
                                ) : (
                                  <ArrowDown size={11} />
                                )}
                              </span>
                            )}
                          </button>
                        </th>
                      ))}
                      <th scope="col">{t("Message")}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {sortedMessages.map((message) => (
                      <tr
                        className={`${message.direction === "tx" ? "tx-row" : ""} ${senderMatchesSelection(message.sender) ? "sender-match selected-row" : ""}`}
                        key={message.id}
                        onClick={() => inspectStation(message.sender)}
                      >
                        <td className="nowrap">{formatDateTime(message.received_at)}</td>
                        <td
                          className={`strong-cell ${message.direction === "tx" ? "tx-sender" : message.sender_source === "offset_inferred" ? "derived-sender" : ""}`}
                          title={
                            message.sender_source === "offset_inferred"
                              ? t("Sender inferred from the most recent station on this offset")
                              : undefined
                          }
                        >
                          <HighlightedText text={message.sender} query={monitorSearch} />
                        </td>
                        <td>{message.band || "—"}</td>
                        <td>
                          <span
                            className={`badge ${message.direction === "tx" ? "tx-traffic-badge" : ""}`}
                          >
                            {message.is_heartbeat ? "HEARTBEAT" : message.type}
                          </span>
                        </td>
                        <td className="snr-cell">
                          {message.snr !== undefined ? `${message.snr} dB` : "—"}
                        </td>
                        <td>{message.offset !== undefined ? `${message.offset} Hz` : "—"}</td>
                        <td>{message.mode || "—"}</td>
                        <td className="message-cell">
                          <HighlightedText text={message.text || "—"} query={monitorSearch} />
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Card>
        </div>
        <MonitorStationInspector
          station={selectedMonitorStation}
          stations={selectedMonitorStations}
          link={selectedMonitorLink}
          links={filteredMapGraph.links}
          onClose={clearInspection}
          onFilterStation={selectedMonitorStation ? toggleStationFilter : undefined}
          filteredCallsign={filteredStationCallsign}
        />
      </div>
    </div>
  );
}

function ChatPanel({
  connected,
  speed,
  onSpeedChange,
}: {
  connected: boolean;
  speed?: number;
  onSpeedChange: (nextSpeed: number) => Promise<void>;
}) {
  const { t } = useLanguage();
  const { formatTime: formatDisplayTime, formatDate } = useTimeDisplay();
  const [chats, setChats] = useState<ChatSummary[]>([]);
  const [stations, setStations] = useState<ChatStation[]>([]);
  const [selectedCallsign, setSelectedCallsign] = useState("");
  const [conversation, setConversation] = useState<ChatMessage[]>([]);
  const [nextCursor, setNextCursor] = useState<string>();
  const [search, setSearch] = useState("");
  const [draft, setDraft] = useState("");
  const [deliveryMode, setDeliveryMode] = useState<DeliveryMode>("best_effort");
  const isGroupChat = selectedCallsign.startsWith("@");
  const [sendSpeed, setSendSpeed] = useState(0);
  const [sendWithEnter, setSendWithEnter] = useState(true);
  const [loading, setLoading] = useState(true);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState("");
  const [contactOpen, setContactOpen] = useState(false);
  const [contact, setContact] = useState<StationContact>({ callsign: "" });
  const [contactSaving, setContactSaving] = useState(false);
  const [newChatOpen, setNewChatOpen] = useState(false);
  const [newChatCallsign, setNewChatCallsign] = useState("");
  const [newChatError, setNewChatError] = useState("");
  const [showArchived, setShowArchived] = useState(false);
  const viewportRef = useRef<HTMLDivElement>(null);

  const loadChats = useCallback(async () => {
    try {
      const [chatData, stationData] = await Promise.all([
        api<{ chats: ChatSummary[]; selected_callsign?: string }>("/api/chats"),
        api<{ stations: ChatStation[] }>("/api/chats/stations"),
      ]);
      setChats(chatData.chats);
      setStations(stationData.stations);
      setSelectedCallsign((current) => {
        if (
          current &&
          chatData.chats.some(
            (chat) => chat.callsign === current && Boolean(chat.archived) === showArchived,
          )
        ) {
          return current;
        }
        const visibleChats = chatData.chats.filter(
          (chat) => Boolean(chat.archived) === showArchived,
        );
        const storedSelection = chatData.chats.find(
          (chat) =>
            chat.callsign === chatData.selected_callsign && Boolean(chat.archived) === showArchived,
        );
        return storedSelection?.callsign || visibleChats[0]?.callsign || "";
      });
    } catch (reason) {
      setError(errorMessage(reason));
    } finally {
      setLoading(false);
    }
  }, [showArchived]);

  const loadConversation = useCallback(
    async (before?: string) => {
      if (!selectedCallsign) {
        setConversation([]);
        return;
      }
      try {
        const query = before ? `?before=${encodeURIComponent(before)}` : "";
        const result = await api<{ messages: ChatMessage[]; next_cursor?: string }>(
          `/api/chats/${encodeURIComponent(selectedCallsign)}/messages${query}`,
        );
        if (before) setConversation((current) => [...result.messages, ...current]);
        else setConversation(result.messages);
        setNextCursor(result.next_cursor);
        await api(`/api/chats/${encodeURIComponent(selectedCallsign)}/read`, { method: "POST" });
        setChats((current) =>
          current.map((chat) =>
            chat.callsign === selectedCallsign ? { ...chat, unread_count: 0 } : chat,
          ),
        );
      } catch (reason) {
        setError(errorMessage(reason));
      }
    },
    [selectedCallsign],
  );

  useEffect(() => {
    void loadChats();
  }, [loadChats]);
  useEffect(() => {
    void loadConversation();
    void api("/api/preferences", {
      method: "PATCH",
      body: JSON.stringify({ selected_chat_callsign: selectedCallsign || null }),
    }).catch(() => undefined);
  }, [loadConversation, selectedCallsign]);
  useEffect(() => {
    const protocol = location.protocol === "https:" ? "wss" : "ws";
    const socket = new WebSocket(`${protocol}://${location.host}/api/events`);
    socket.onmessage = (event) => {
      try {
        const payload = JSON.parse(event.data) as {
          event?: string;
          data?: {
            id?: number;
            callsign?: string;
            text?: string;
            from_callsign?: string;
            to_callsign?: string;
            snr?: number;
            mode?: string;
            band?: string;
            offset?: number;
            timestamp?: string;
            is_duplicate?: boolean;
            delivery_mode?: string;
            protocol_id?: string;
          };
        };
        const eventName = (payload.event ?? "").toLowerCase();

        if (
          eventName === "chat.message.received" &&
          payload.data?.callsign === selectedCallsign &&
          !payload.data.is_duplicate
        ) {
          // Prepend the new message directly to the conversation.
          const newMsg: ChatMessage = {
            id: `rx-${payload.data.id || Date.now()}`,
            callsign: payload.data.callsign || "",
            from_callsign: payload.data.from_callsign || null,
            direction: "rx",
            text: payload.data.text || "",
            timestamp: payload.data.timestamp || new Date().toISOString(),
            status: "received",
            snr: payload.data.snr,
            mode: payload.data.mode,
            band: payload.data.band,
            offset: payload.data.offset,
            delivery_mode: (payload.data.delivery_mode as DeliveryMode) || "best_effort",
            protocol_id: payload.data.protocol_id || undefined,
          };
          setConversation((current) => [...current, newMsg]);
          void loadChats();
          return;
        }

        if (eventName === "chat.message.sent" && payload.data?.callsign === selectedCallsign) {
          // Sent message — prepend a TX entry.
          const txMsg: ChatMessage = {
            id: `tx-${payload.data.id || Date.now()}`,
            callsign: payload.data.callsign || "",
            from_callsign: null,
            direction: "tx",
            text: payload.data.text || "",
            timestamp: new Date().toISOString(),
            status: "sent",
            delivery_mode: (payload.data.delivery_mode as DeliveryMode) || "best_effort",
            protocol_id: payload.data.protocol_id || undefined,
          };
          setConversation((current) => [...current, txMsg]);
          void loadChats();
          return;
        }

        // Fallback: reload for any other chat/activity event.
        if (
          payload.event?.startsWith("rx.") ||
          payload.event?.startsWith("tx.") ||
          payload.event?.startsWith("chat.")
        ) {
          void loadChats();
          if (selectedCallsign) void loadConversation();
        }
      } catch {
        // Ignore non-chat events.
      }
    };
    const fallbackTimer = window.setInterval(() => {
      void loadChats();
      if (selectedCallsign) void loadConversation();
    }, 30_000);
    return () => {
      socket.close();
      window.clearInterval(fallbackTimer);
    };
  }, [loadChats, loadConversation, selectedCallsign]);
  useEffect(() => {
    const viewport = viewportRef.current;
    if (viewport) viewport.scrollTop = viewport.scrollHeight;
  }, [conversation.length, selectedCallsign]);

  const archiveChat = async (callsign: string, archived: boolean) => {
    try {
      await api(`/api/chats/${encodeURIComponent(callsign)}/archive`, {
        method: "POST",
        body: JSON.stringify({ enabled: archived }),
      });
      setChats((current) =>
        current.map((chat) => (chat.callsign === callsign ? { ...chat, archived } : chat)),
      );
      if (callsign === selectedCallsign && archived) setSelectedCallsign("");
    } catch (reason) {
      setError(errorMessage(reason));
    }
  };

  const filteredChats = chats.filter((chat) => {
    const needle = search.trim().toUpperCase();
    return (
      Boolean(chat.archived) === showArchived &&
      (!needle ||
        chat.callsign.includes(needle) ||
        chat.last_message.toUpperCase().includes(needle))
    );
  });
  const stationMatches = stations.filter((station) => {
    const needle = search.trim().toUpperCase();
    return needle && station.callsign.includes(needle);
  });
  const selectedChat = chats.find((chat) => chat.callsign === selectedCallsign);
  const selectedChatSpeed = selectedChat?.preferred_speed ?? speed ?? 0;
  const selectedStation = stations.find((station) => station.callsign === selectedCallsign);
  const recentStations = [...stations].sort((left, right) =>
    String(right.last_seen || "").localeCompare(String(left.last_seen || "")),
  );
  useEffect(() => {
    setSendSpeed(selectedChatSpeed);
  }, [selectedCallsign, selectedChatSpeed]);
  useEffect(() => {
    if (!selectedCallsign) return;
    void api<StationContact>(`/api/stations/${encodeURIComponent(selectedCallsign)}`)
      .then(setContact)
      .catch(() => setContact({ callsign: selectedCallsign }));
  }, [selectedCallsign]);
  const formatTime = (value: string) => formatDisplayTime(value);
  const statusLabel = (status: string) => {
    if (status === "queued") return t("In wachtrij");
    if (status === "transmitting") return t("Wordt verzonden");
    if (status === "awaiting_ack") return t("Ontvangstbevestiging afwachten");
    if (status === "retrying") return t("Opnieuw verzenden");
    if (status === "delivered") return t("Afgeleverd");
    if (status === "sent") return t("Verzonden via radio");
    if (status === "failed") return t("Mislukt");
    return status;
  };
  function selectChat(callsign: string) {
    const normalizedCallsign = callsign.toUpperCase();
    setSelectedCallsign(normalizedCallsign);
    setSearch("");
    if (connected) {
      void api("/api/js8/call-selected", {
        method: "PATCH",
        body: JSON.stringify({ callsign: normalizedCallsign }),
      }).catch((reason) => setError(errorMessage(reason)));
    }
  }
  function openNewChat() {
    setNewChatCallsign("");
    setNewChatError("");
    setNewChatOpen(true);
  }
  function startNewChat() {
    const callsign = newChatCallsign.trim().toUpperCase();
    if (!/^[A-Z0-9][A-Z0-9/-]{1,31}$/.test(callsign)) {
      setNewChatError(t("Voer een geldige callsign in."));
      return;
    }
    selectChat(callsign);
    setNewChatOpen(false);
  }
  async function sendChatMessage() {
    if (!selectedCallsign || !draft.trim() || sending || !connected) return;
    setSending(true);
    setError("");
    // Group destinations only support best-effort delivery.
    const isGroup = selectedCallsign.startsWith("@");
    const mode: DeliveryMode = isGroup ? "best_effort" : deliveryMode;
    try {
      if (sendSpeed !== speed) {
        await onSpeedChange(sendSpeed);
      }
      await api(`/api/chats/${encodeURIComponent(selectedCallsign)}/messages`, {
        method: "POST",
        body: JSON.stringify({ text: draft.trim(), delivery_mode: mode }),
      });
      setDraft("");
      await loadConversation();
      await loadChats();
    } catch (reason) {
      setError(errorMessage(reason));
    } finally {
      setSending(false);
    }
  }
  async function changeChatSpeed(nextSpeed: number) {
    if (!selectedCallsign) return;
    setSendSpeed(nextSpeed);
    setChats((current) =>
      current.map((chat) =>
        chat.callsign === selectedCallsign ? { ...chat, preferred_speed: nextSpeed } : chat,
      ),
    );
    try {
      await api(`/api/chats/${encodeURIComponent(selectedCallsign)}/speed`, {
        method: "PATCH",
        body: JSON.stringify({ speed: nextSpeed }),
      });
    } catch (reason) {
      setError(errorMessage(reason));
    }
  }
  async function saveContact() {
    if (!selectedCallsign || contactSaving) return;
    setContactSaving(true);
    setError("");
    try {
      const saved = await api<StationContact>(
        `/api/stations/${encodeURIComponent(selectedCallsign)}`,
        {
          method: "PATCH",
          body: JSON.stringify({
            name: contact.name || null,
            qth: contact.qth || null,
            notes: contact.notes || null,
          }),
        },
      );
      setContact(saved);
      setContactOpen(false);
    } catch (reason) {
      setError(errorMessage(reason));
    } finally {
      setContactSaving(false);
    }
  }
  return (
    <div className="chat-shell">
      <aside className={`chat-sidebar ${selectedCallsign ? "has-selection" : ""}`}>
        <div className="chat-sidebar-header">
          <div>
            <h2>{t("Chats")}</h2>
            <span className="muted">
              {filteredChats.length}{" "}
              {t(showArchived ? "gearchiveerde gesprekken" : "conversations")}
            </span>
          </div>
          <div className="chat-sidebar-actions">
            <button
              type="button"
              className="chat-icon-button"
              onClick={() => setShowArchived((current) => !current)}
              title={showArchived ? t("Actieve chats tonen") : t("Gearchiveerde chats tonen")}
              aria-label={showArchived ? t("Actieve chats tonen") : t("Gearchiveerde chats tonen")}
            >
              {showArchived ? <ArchiveRestore size={16} /> : <Archive size={16} />}
            </button>
            <Button className="chat-new-button" onClick={openNewChat} title={t("Nieuwe chat")}>
              <Plus size={17} aria-hidden="true" />
              <span>{t("Nieuwe chat")}</span>
            </Button>
          </div>
        </div>
        <Input
          aria-label={t("Zoek chats of callsign…")}
          value={search}
          onChange={(event) => setSearch(event.target.value)}
          placeholder={t("Zoek chats of callsign…")}
        />
        <div className="chat-list">
          {stationMatches
            .filter((station) => !chats.some((chat) => chat.callsign === station.callsign))
            .slice(0, 5)
            .map((station) => (
              <button
                type="button"
                className="chat-list-item"
                key={station.callsign}
                onClick={() => selectChat(station.callsign)}
              >
                <span className="chat-presence available" aria-hidden="true" />
                <span className="chat-avatar">{station.callsign.slice(0, 2)}</span>
                <span className="chat-list-copy">
                  <strong>{station.callsign}</strong>
                  <small>{t("Nieuwe chat")}</small>
                </span>
              </button>
            ))}
          {loading ? (
            <p className="muted chat-empty">{t("Chats laden…")}</p>
          ) : filteredChats.length === 0 && !stationMatches.length ? (
            <p className="muted chat-empty">{t("Nog geen chats")}</p>
          ) : null}
          {filteredChats.map((chat) => (
            <div
              className={`chat-list-item ${chat.callsign === selectedCallsign ? "selected" : ""}`}
              key={chat.callsign}
            >
              <button
                type="button"
                className="chat-list-main"
                onClick={() => selectChat(chat.callsign)}
              >
                <span
                  className={`chat-presence ${
                    chat.unread_count > 0 ? "rx" : chat.last_direction === "tx" ? "tx" : "ok"
                  }`}
                  aria-label={t(
                    chat.unread_count > 0
                      ? "Ongelezen ontvangen bericht"
                      : chat.last_direction === "tx"
                        ? "Laatste activiteit verzonden"
                        : "Alles gelezen",
                  )}
                  title={t(
                    chat.unread_count > 0
                      ? "Ongelezen ontvangen bericht"
                      : chat.last_direction === "tx"
                        ? "Laatste activiteit verzonden"
                        : "Alles gelezen",
                  )}
                />
                <span className="chat-avatar">{chat.callsign.slice(0, 2)}</span>
                <span className="chat-list-copy">
                  <strong>{chat.callsign}</strong>
                  <small>{chat.last_message}</small>
                </span>
                <span className="chat-list-meta">
                  <small className={`chat-direction-badge ${chat.last_direction}`}>
                    {chat.last_direction === "tx" ? (
                      <IconArrowUpRight size={11} aria-hidden="true" />
                    ) : (
                      <IconArrowDownLeft size={11} aria-hidden="true" />
                    )}
                    {chat.last_direction.toUpperCase()}
                  </small>
                  <small>{formatTime(chat.last_message_at)}</small>
                  {chat.unread_count > 0 && (
                    <span className="unread-badge">{chat.unread_count}</span>
                  )}
                </span>
              </button>
              <button
                type="button"
                className="chat-archive-button"
                onClick={() => void archiveChat(chat.callsign, !chat.archived)}
                title={chat.archived ? t("Chat herstellen") : t("Chat archiveren")}
                aria-label={chat.archived ? t("Chat herstellen") : t("Chat archiveren")}
              >
                {chat.archived ? <ArchiveRestore size={15} /> : <Archive size={15} />}
              </button>
            </div>
          ))}
        </div>
      </aside>
      <section className={`chat-conversation ${selectedCallsign ? "active" : ""}`}>
        {!selectedCallsign ? (
          <div className="chat-welcome">
            <span className="chat-welcome-icon">
              <MessagesSquare size={24} aria-hidden="true" />
            </span>
            <h2>{t("Selecteer een chat")}</h2>
            <p className="muted">{t("Kies een station om berichten uit te wisselen.")}</p>
          </div>
        ) : (
          <>
            <header className="chat-conversation-header">
              <button
                type="button"
                className="chat-back-button"
                onClick={() => setSelectedCallsign("")}
                aria-label={t("Terug")}
              >
                <ChevronLeft size={20} aria-hidden="true" />
              </button>
              <span className="chat-avatar large">{selectedCallsign.slice(0, 2)}</span>
              <div>
                <h2>{selectedCallsign}</h2>
                <small className="muted">
                  {selectedChat?.grid || selectedStation?.grid || t("Geen grid")}
                  {selectedChat?.last_mode ? ` · ${selectedChat.last_mode}` : ""}
                  {selectedChat?.last_offset ? ` · ${selectedChat.last_offset} Hz` : ""}
                  {(selectedChat?.last_snr ?? selectedStation?.last_snr) != null
                    ? ` · ${selectedChat?.last_snr ?? selectedStation?.last_snr} dB SNR`
                    : ""}
                </small>
              </div>
              <span
                className={`js8link-protocol-status ${
                  selectedChat?.js8link_capable || selectedStation?.js8link_capable
                    ? "supported"
                    : "unknown"
                }`}
                title={
                  selectedChat?.js8link_capable || selectedStation?.js8link_capable
                    ? t("Dit station ondersteunt JS8Link ARQ")
                    : t("JS8Link-status van dit station is nog onbekend")
                }
              >
                {selectedChat?.js8link_capable || selectedStation?.js8link_capable
                  ? "↔ JS8Link"
                  : `? ${t("JS8Link onbekend")}`}
              </span>
            </header>
            <MessageScrollerProvider>
              <MessageScroller className="chat-transcript">
                <MessageScrollerViewport viewportRef={viewportRef}>
                  <MessageScrollerContent>
                    {nextCursor && (
                      <Button
                        className="chat-load-more"
                        onClick={() => void loadConversation(nextCursor)}
                      >
                        {t("Oudere berichten laden")}
                      </Button>
                    )}
                    {conversation.length === 0 ? (
                      <p className="muted chat-empty">{t("Nog geen berichten in deze chat")}</p>
                    ) : (
                      conversation.map((message, index) => {
                        const previous = conversation[index - 1];
                        const newDay =
                          !previous ||
                          formatDate(previous.timestamp) !== formatDate(message.timestamp);
                        return (
                          <MessageGroup key={message.id}>
                            {newDay && (
                              <div className="chat-date-marker">
                                {formatDate(message.timestamp)}
                              </div>
                            )}
                            <MessageScrollerItem messageId={message.id}>
                              <Message
                                direction={message.direction === "tx" ? "outgoing" : "incoming"}
                              >
                                <MessageAvatar>
                                  <span className="chat-avatar small">
                                    {message.direction === "tx"
                                      ? "ME"
                                      : isGroupChat && message.from_callsign
                                        ? message.from_callsign.slice(0, 2)
                                        : selectedCallsign.slice(0, 2)}
                                  </span>
                                </MessageAvatar>
                                <MessageContent>
                                  <MessageHeader>
                                    <span className={`message-direction ${message.direction}`}>
                                      {message.direction === "tx" ? (
                                        <IconArrowUpRight size={11} aria-hidden="true" />
                                      ) : (
                                        <IconArrowDownLeft size={11} aria-hidden="true" />
                                      )}
                                      {message.direction.toUpperCase()}
                                    </span>
                                    {message.direction === "tx"
                                      ? t("Jij")
                                      : isGroupChat && message.from_callsign
                                        ? message.from_callsign
                                        : selectedCallsign}
                                  </MessageHeader>
                                  <Bubble>
                                    <BubbleContent>{message.text}</BubbleContent>
                                  </Bubble>
                                  <MessageFooter>
                                    {formatTime(message.timestamp)}
                                    {message.direction === "tx"
                                      ? ` · ${statusLabel(message.status)}`
                                      : message.snr !== undefined
                                        ? ` · ${message.snr} dB`
                                        : ""}
                                  </MessageFooter>
                                </MessageContent>
                              </Message>
                            </MessageScrollerItem>
                          </MessageGroup>
                        );
                      })
                    )}
                  </MessageScrollerContent>
                </MessageScrollerViewport>
                <MessageScrollerButton
                  onClick={() => {
                    if (viewportRef.current)
                      viewportRef.current.scrollTop = viewportRef.current.scrollHeight;
                  }}
                />
              </MessageScroller>
            </MessageScrollerProvider>
            <div className="chat-composer">
              <div className="chat-composer-entry chat-composer-entry-modern">
                <Textarea
                  aria-label={t("Typ een bericht")}
                  value={draft}
                  disabled={!connected || sending}
                  maxLength={220}
                  onChange={(event) => setDraft(event.target.value)}
                  onKeyDown={(event) => {
                    if (sendWithEnter && event.key === "Enter" && !event.shiftKey) {
                      event.preventDefault();
                      void sendChatMessage();
                    }
                  }}
                  placeholder={connected ? t("Typ een bericht…") : t("Niet verbonden met JS8Call")}
                />
                <div className="chat-composer-toolbar">
                  <span className="chat-character-count">{draft.length} / 220</span>
                  <label className="chat-enter-toggle">
                    <input
                      type="checkbox"
                      checked={sendWithEnter}
                      onChange={(event) => setSendWithEnter(event.target.checked)}
                    />
                    {t("Verzenden met Enter")}
                  </label>
                  <span className="chat-composer-toolbar-spacer" />
                  <label className="chat-composer-select-label" htmlFor="chat-send-speed">
                    {t("Snelheid")}
                    <Select
                      id="chat-send-speed"
                      className="chat-composer-select"
                      value={sendSpeed}
                      onChange={(event) => void changeChatSpeed(Number(event.target.value))}
                    >
                      <option value={0}>NORMAL</option>
                      <option value={1}>FAST</option>
                      <option value={2}>TURBO</option>
                      <option value={4}>SLOW</option>
                      <option value={8}>JS8</option>
                    </Select>
                  </label>
                  {!isGroupChat && (
                    <label className="chat-composer-select-label" htmlFor="chat-delivery-mode">
                      {t("Aflevermethode")}
                      <Select
                        id="chat-delivery-mode"
                        className="chat-composer-select"
                        value={deliveryMode}
                        onChange={(event) => setDeliveryMode(event.target.value as DeliveryMode)}
                      >
                        <option value="best_effort">{t("Best effort")}</option>
                        <option value="confirmed">{t("Bevestigde aflevering")}</option>
                      </Select>
                    </label>
                  )}
                  {isGroupChat && (
                    <span className="chat-composer-group-notice">
                      {t("Groepsbericht (best effort)")}
                    </span>
                  )}
                  <Button
                    className="chat-send-button"
                    disabled={!connected || sending || !draft.trim()}
                    onClick={() => void sendChatMessage()}
                  >
                    <IconArrowUpRight size={16} aria-hidden="true" />
                    {sending
                      ? "…"
                      : !isGroupChat && deliveryMode === "confirmed"
                        ? t("Bevestigd verzenden")
                        : t("Verzenden")}
                  </Button>
                </div>
              </div>
            </div>
          </>
        )}
      </section>
      {selectedCallsign && (
        <aside className="station-inspector" aria-label={t("Stationinformatie")}>
          <div className="station-inspector-header">
            <div>
              <span className="panel-eyebrow">{t("Stationinformatie")}</span>
              <h2>{selectedCallsign}</h2>
              <p>{contact.name || selectedStation?.name || t("Naam niet vastgelegd")}</p>
            </div>
            {contactOpen ? (
              <div className="station-inspector-edit-actions">
                <Button className="station-inspector-edit" onClick={() => setContactOpen(false)}>
                  {t("Annuleren")}
                </Button>
                <Button
                  className="station-inspector-edit primary"
                  disabled={contactSaving}
                  onClick={() => void saveContact()}
                >
                  {contactSaving ? t("Opslaan…") : t("Opslaan")}
                </Button>
              </div>
            ) : (
              <Button
                className="station-inspector-edit"
                title={t("Stationinformatie bewerken")}
                aria-label={t("Stationinformatie bewerken")}
                onClick={() => setContactOpen(true)}
              >
                <Pencil size={17} aria-hidden="true" />
              </Button>
            )}
          </div>
          {contactOpen && (
            <section className="station-inspector-section station-contact-form">
              <h3>{t("Stationinformatie bewerken")}</h3>
              <Label>{t("Naam van de operator")}</Label>
              <Input
                value={contact.name || ""}
                onChange={(event) =>
                  setContact((current) => ({ ...current, name: event.target.value }))
                }
                placeholder={t("Naam van de operator")}
              />
              <Label>{t("QTH")}</Label>
              <Input
                value={contact.qth || ""}
                onChange={(event) =>
                  setContact((current) => ({ ...current, qth: event.target.value }))
                }
                placeholder={t("Plaats of locatie")}
              />
              <Label>{t("Aantekeningen")}</Label>
              <Textarea
                value={contact.notes || ""}
                onChange={(event) =>
                  setContact((current) => ({ ...current, notes: event.target.value }))
                }
                placeholder={t("Persoonlijke aantekeningen")}
              />
            </section>
          )}
          <section className="station-inspector-section">
            <h3>{t("Station")}</h3>
            <dl className="station-data-list">
              <div>
                <dt>{t("Grid")}</dt>
                <dd>{selectedChat?.grid || selectedStation?.grid || "--"}</dd>
              </div>
              <div>
                <dt>{t("QTH")}</dt>
                <dd>{contact.qth || selectedStation?.qth || "--"}</dd>
              </div>
            </dl>
          </section>
          <section className="station-inspector-section">
            <h3>{t("Signaal")}</h3>
            <dl className="station-data-list station-data-grid">
              <div>
                <dt>{t("Last SNR")}</dt>
                <dd>
                  {selectedChat?.last_snr ?? selectedStation?.last_snr ?? "--"}
                  {(selectedChat?.last_snr ?? selectedStation?.last_snr) !== undefined ? " dB" : ""}
                </dd>
              </div>
              <div>
                <dt>{t("Offset")}</dt>
                <dd>
                  {selectedChat?.last_offset ?? selectedStation?.last_offset ?? "--"}
                  {(selectedChat?.last_offset ?? selectedStation?.last_offset) !== undefined
                    ? " Hz"
                    : ""}
                </dd>
              </div>
              <div>
                <dt>{t("Mode")}</dt>
                <dd>{selectedChat?.last_mode || selectedStation?.last_mode || "--"}</dd>
              </div>
              <div>
                <dt>{t("Last heard")}</dt>
                <dd>
                  {selectedChat?.last_heard_at || selectedStation?.last_seen
                    ? `${formatDate(
                        selectedChat?.last_heard_at || selectedStation?.last_seen || "",
                      )} ${formatTime(
                        selectedChat?.last_heard_at || selectedStation?.last_seen || "",
                      )}`
                    : "--"}
                </dd>
              </div>
            </dl>
          </section>
          <section className="station-inspector-section">
            <h3>{t("Protocol")}</h3>
            <div
              className={`protocol-readout ${
                selectedChat?.js8link_capable || selectedStation?.js8link_capable
                  ? "supported"
                  : "unknown"
              }`}
            >
              <strong>JS8Link</strong>
              <span>
                {selectedChat?.js8link_capable || selectedStation?.js8link_capable
                  ? t("Ondersteund")
                  : t("Onbekend")}
              </span>
            </div>
          </section>
          <section className="station-inspector-section station-notes">
            <h3>{t("Aantekeningen")}</h3>
            <p>{contact.notes || t("Nog geen aantekeningen.")}</p>
          </section>
        </aside>
      )}
      {newChatOpen && (
        <div
          className="modal-backdrop"
          role="presentation"
          onMouseDown={() => setNewChatOpen(false)}
        >
          <div
            className="modal-card new-chat-modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="new-chat-title"
            onMouseDown={(event) => event.stopPropagation()}
          >
            <div className="modal-header">
              <div>
                <h2 id="new-chat-title">{t("Nieuwe chat")}</h2>
                <p className="muted">
                  {t("Kies een laatst gehoord station of voer zelf een callsign in.")}
                </p>
              </div>
              <Button
                className="modal-close"
                onClick={() => setNewChatOpen(false)}
                aria-label={t("Sluiten")}
              >
                <X size={18} aria-hidden="true" />
              </Button>
            </div>
            <div className="stack">
              <Label>
                {t("Laatst gehoorde stations")}
                <Select
                  value={
                    recentStations.some((station) => station.callsign === newChatCallsign)
                      ? newChatCallsign
                      : ""
                  }
                  onChange={(event) => {
                    setNewChatCallsign(event.target.value);
                    setNewChatError("");
                  }}
                >
                  <option value="">{t("Kies een station…")}</option>
                  {recentStations.map((station) => (
                    <option key={station.callsign} value={station.callsign}>
                      {station.callsign}
                      {station.grid ? ` · ${station.grid}` : ""}
                      {station.last_snr !== undefined ? ` · ${station.last_snr} dB` : ""}
                    </option>
                  ))}
                </Select>
              </Label>
              {recentStations.length === 0 && (
                <small className="muted">{t("Er zijn nog geen laatst gehoorde stations.")}</small>
              )}
              <div className="new-chat-separator">
                <span>{t("of")}</span>
              </div>
              <Label>
                {t("Callsign handmatig invoeren")}
                <Input
                  value={newChatCallsign}
                  maxLength={32}
                  autoCapitalize="characters"
                  autoFocus
                  onChange={(event) => {
                    setNewChatCallsign(event.target.value.toUpperCase());
                    setNewChatError("");
                  }}
                  onKeyDown={(event) => {
                    if (event.key === "Enter") startNewChat();
                  }}
                  placeholder="PA0ABC"
                />
              </Label>
              {newChatError && (
                <div className="error" role="alert">
                  {newChatError}
                </div>
              )}
            </div>
            <div className="modal-actions">
              <Button onClick={() => setNewChatOpen(false)}>{t("Annuleren")}</Button>
              <Button className="primary" disabled={!newChatCallsign.trim()} onClick={startNewChat}>
                {t("Chat starten")}
              </Button>
            </div>
          </div>
        </div>
      )}
      {error && <div className="error chat-error">{error}</div>}
    </div>
  );
}

function MessagesPanel() {
  const { t } = useLanguage();
  const [syncing, setSyncing] = useState(false);
  const [syncMessage, setSyncMessage] = useState("");
  const [syncError, setSyncError] = useState("");
  async function syncInbox() {
    setSyncing(true);
    setSyncMessage("");
    setSyncError("");
    try {
      const result = await api<{ synced: number }>("/api/js8/inbox/sync", { method: "POST" });
      setSyncMessage(`${t("Inbox bijgewerkt")}: ${result.synced}`);
    } catch (reason) {
      setSyncError(errorMessage(reason));
    } finally {
      setSyncing(false);
    }
  }
  return (
    <Card className="wide messages-console">
      <header className="workspace-titlebar">
        <div className="panel-title-with-icon">
          <MessagesSquare size={18} aria-hidden="true" />
          <div>
            <span className="panel-eyebrow">{t("Station messaging")}</span>
            <h2>{t("Messages")}</h2>
            <p>{t("Stored station-to-station messages and delivery queues.")}</p>
          </div>
        </div>
        <div className="message-console-stats">
          <div>
            <span>{t("Inbox")}</span>
            <strong>--</strong>
          </div>
          <div>
            <span>{t("Outbox")}</span>
            <strong>--</strong>
          </div>
          <div className="tx">
            <span>{t("TX queue")}</span>
            <strong>0</strong>
          </div>
          <Button className="secondary" onClick={() => void syncInbox()} disabled={syncing}>
            {syncing ? t("Synchroniseren…") : t("Inbox synchroniseren")}
          </Button>
        </div>
      </header>
      {(syncMessage || syncError) && (
        <div
          className={syncError ? "error messages-sync-status" : "success-text messages-sync-status"}
        >
          {syncError || syncMessage}
        </div>
      )}
      <div className="messages-placeholder">
        <div className="messages-placeholder-icon" aria-hidden="true">
          <MessagesSquare size={28} />
        </div>
        <span className="messages-placeholder-badge">{t("Binnenkort")}</span>
        <h2>{t("Messages")}</h2>
        <p className="muted">
          {t(
            "Deze pagina wordt later toegevoegd. Hier komen opgeslagen berichten tussen stations te staan.",
          )}
        </p>
        <div className="messages-feature-strip" aria-label={t("Planned message functions")}>
          <span>ARQ</span>
          <span>{t("Inbox")}</span>
          <span>{t("Delivery status")}</span>
        </div>
      </div>
    </Card>
  );
}

function SettingsPanel({ setup, onSaved }: { setup: Setup; onSaved: () => void }) {
  const { language, setLanguage, t } = useLanguage();
  const { theme, setTheme } = useTheme();
  const { timeDisplay, setTimeDisplay } = useTimeDisplay();
  const [host, setHost] = useState(setup.host);
  const [port, setPort] = useState(String(setup.port));
  const [retentionDays, setRetentionDays] = useState(90);
  const [bandScopeMinutes, setBandScopeMinutes] = useState("15");
  const [apiMessageRetentionDays, setApiMessageRetentionDays] = useState(7);
  const [diagnosticsEnabled, setDiagnosticsEnabled] = useState(true);
  const [diagnosticsRetentionDays, setDiagnosticsRetentionDays] = useState(7);
  const [mapPopups, setMapPopups] = useState(true);
  const [mapGreyline, setMapGreyline] = useState(true);
  const [mapBidirectionalOnly, setMapBidirectionalOnly] = useState(false);
  const [mapClusterStations, setMapClusterStations] = useState(true);
  const [toastDurationSeconds, setToastDurationSeconds] = useState(5);
  const [authEnabled, setAuthEnabled] = useState(setup.auth_enabled);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [js8, setJs8] = useState<JS8Settings>();
  const [js8Filter, setJs8Filter] = useState<JS8Filter>();
  const [txQueue, setTxQueue] = useState<TxQueueStatus>();
  const [txBuffer, setTxBuffer] = useState("");
  const [js8AuxSaving, setJs8AuxSaving] = useState(false);
  const [frequencyPresets, setFrequencyPresets] = useState<FrequencyPreset[]>([]);
  const [js8Saving, setJs8Saving] = useState(false);
  const [js8Error, setJs8Error] = useState("");
  const [updateRepository, setUpdateRepository] = useState("");
  const [updateBranch, setUpdateBranch] = useState("main");
  const [updateInfo, setUpdateInfo] = useState<UpdateInfo>();
  const [updateChecking, setUpdateChecking] = useState(false);
  const [updateApplying, setUpdateApplying] = useState(false);
  const [updateConfirmation, setUpdateConfirmation] = useState(false);
  const [updateError, setUpdateError] = useState("");
  const [updateResult, setUpdateResult] = useState<UpdateResult>();
  const [querySettings, setQuerySettings] = useState<QuerySettings>({
    station_queries_enabled: true,
    query_interval_snr_minutes: 60,
    query_interval_hearing_minutes: 60,
    query_interval_info_days: 14,
    query_interval_grid_days: 14,
    query_interval_status_hours: 24,
    query_max_per_hour: 12,
    query_cooldown_seconds: 120,
    query_timeout_minutes: 5,
  });
  const [settingsTab, setSettingsTab] = useState<"application" | "js8call" | "diagnostics">(
    "application",
  );
  const [purgeConfirmation, setPurgeConfirmation] = useState(false);
  const [purging, setPurging] = useState(false);
  const [purgeMessage, setPurgeMessage] = useState("");

  useEffect(() => {
    void api<JS8Settings>("/api/js8/settings")
      .then(setJs8)
      .catch((reason) => setJs8Error(errorMessage(reason)));
    void api<JS8Filter>("/api/js8/filter")
      .then(setJs8Filter)
      .catch(() => undefined);
    void api<TxQueueStatus>("/api/js8/tx-queue")
      .then(setTxQueue)
      .catch(() => undefined);
    void api<{ text: string }>("/api/js8/tx-text")
      .then((result) => setTxBuffer(result.text))
      .catch(() => undefined);
    void Promise.all([
      api<FrequencyPreset[]>("/api/js8/frequency-presets"),
      api<{
        received_message_retention_days: number;
        band_scope_minutes: number;
        monitor_map_popups: boolean;
        monitor_map_greyline: boolean;
        monitor_map_bidirectional_only: boolean;
        monitor_map_cluster_stations: boolean;
        toast_duration_seconds: number;
      }>("/api/preferences"),
      api<
        {
          update_repository?: string | null;
          update_branch?: string;
          api_message_retention_days?: number;
          diagnostics_enabled?: boolean;
          diagnostics_retention_days?: number;
          toast_duration_seconds?: number;
        } & QuerySettings
      >("/api/config"),
    ])
      .then(([presets, preferences, config]) => {
        setFrequencyPresets(presets);
        setRetentionDays(preferences.received_message_retention_days);
        setBandScopeMinutes(String(preferences.band_scope_minutes ?? 15));
        setMapPopups(preferences.monitor_map_popups);
        setMapGreyline(preferences.monitor_map_greyline);
        setMapBidirectionalOnly(preferences.monitor_map_bidirectional_only);
        setMapClusterStations(preferences.monitor_map_cluster_stations);
        setToastDurationSeconds(preferences.toast_duration_seconds ?? 5);
        setUpdateRepository(config.update_repository || "");
        setUpdateBranch(config.update_branch || "main");
        setApiMessageRetentionDays(config.api_message_retention_days ?? 7);
        setDiagnosticsEnabled(config.diagnostics_enabled ?? true);
        setDiagnosticsRetentionDays(config.diagnostics_retention_days ?? 7);
        setQuerySettings({
          station_queries_enabled: config.station_queries_enabled ?? true,
          query_interval_snr_minutes: config.query_interval_snr_minutes ?? 60,
          query_interval_hearing_minutes: config.query_interval_hearing_minutes ?? 60,
          query_interval_info_days: config.query_interval_info_days ?? 14,
          query_interval_grid_days: config.query_interval_grid_days ?? 14,
          query_interval_status_hours: config.query_interval_status_hours ?? 24,
          query_max_per_hour: config.query_max_per_hour ?? 12,
          query_cooldown_seconds: config.query_cooldown_seconds ?? 120,
          query_timeout_minutes: config.query_timeout_minutes ?? 5,
        });
      })
      .catch((reason) => setError(errorMessage(reason)));
  }, []);

  useEffect(() => {
    if (settingsTab !== "js8call") return;
    const refresh = () => {
      void api<TxQueueStatus>("/api/js8/tx-queue")
        .then(setTxQueue)
        .catch(() => undefined);
      void api<{ text: string }>("/api/js8/tx-text")
        .then((result) => setTxBuffer(result.text))
        .catch(() => undefined);
    };
    const timer = window.setInterval(refresh, 10_000);
    return () => window.clearInterval(timer);
  }, [settingsTab]);

  async function save() {
    setSaving(true);
    setError("");
    try {
      await Promise.all([
        api("/api/config", {
          method: "PATCH",
          body: JSON.stringify({
            host,
            port: Number(port),
            auth_enabled: authEnabled,
            username: authEnabled ? username || undefined : undefined,
            password: password || undefined,
            update_branch: updateBranch.trim() || "main",
            ...querySettings,
            api_message_retention_days: apiMessageRetentionDays,
            diagnostics_enabled: diagnosticsEnabled,
            diagnostics_retention_days: diagnosticsRetentionDays,
            toast_duration_seconds: toastDurationSeconds,
          }),
        }),
        api("/api/preferences", {
          method: "PATCH",
          body: JSON.stringify({
            received_message_retention_days: retentionDays,
            band_scope_minutes: clampBandScopeMinutes(bandScopeMinutes),
            monitor_map_popups: mapPopups,
            monitor_map_greyline: mapGreyline,
            monitor_map_bidirectional_only: mapBidirectionalOnly,
            monitor_map_cluster_stations: mapClusterStations,
          }),
        }),
      ]);
      setPassword("");
      onSaved();
    } catch (e) {
      setError(String(e));
    } finally {
      setSaving(false);
    }
  }

  async function checkForUpdates() {
    setUpdateChecking(true);
    setUpdateError("");
    setUpdateInfo(undefined);
    setUpdateResult(undefined);
    setUpdateConfirmation(false);
    try {
      await api("/api/config", {
        method: "PATCH",
        body: JSON.stringify({
          update_branch: updateBranch.trim() || "main",
        }),
      });
      setUpdateInfo(await api<UpdateInfo>("/api/update/check"));
    } catch (reason) {
      setUpdateError(errorMessage(reason));
    } finally {
      setUpdateChecking(false);
    }
  }

  async function applyUpdate() {
    setUpdateApplying(true);
    setUpdateError("");
    try {
      const result = await api<UpdateResult>("/api/update/apply", { method: "POST" });
      setUpdateResult(result);
      setUpdateConfirmation(false);
      if (result.restart_scheduled) {
        window.setTimeout(() => window.location.reload(), 8000);
      }
    } catch (reason) {
      setUpdateError(errorMessage(reason));
    } finally {
      setUpdateApplying(false);
    }
  }

  async function purgeData() {
    setPurging(true);
    setPurgeMessage("");
    try {
      await api("/api/data/purge", { method: "POST" });
      // Force a full, uncached page reload so every panel fetches fresh data.
      // Using location.replace with the current URL avoids caching issues.
      window.location.replace(window.location.href);
    } catch (reason) {
      setError(errorMessage(reason));
    } finally {
      setPurging(false);
    }
  }

  async function saveJs8() {
    if (!js8) return;
    setJs8Saving(true);
    setJs8Error("");
    try {
      const updated = await api<JS8Settings>("/api/js8/settings", {
        method: "PATCH",
        body: JSON.stringify(js8),
      });
      setJs8(updated);
    } catch (e) {
      setJs8Error(String(e));
    } finally {
      setJs8Saving(false);
    }
  }

  async function saveJs8Auxiliary() {
    if (!js8Filter) return;
    setJs8AuxSaving(true);
    setJs8Error("");
    try {
      const [filter] = await Promise.all([
        api<JS8Filter>("/api/js8/filter", {
          method: "PATCH",
          body: JSON.stringify({ center: js8Filter.center, width: js8Filter.width }),
        }),
        api("/api/js8/filter/enabled", {
          method: "POST",
          body: JSON.stringify({ enabled: js8Filter.enabled ?? true }),
        }),
        api("/api/js8/tx-text", {
          method: "POST",
          body: JSON.stringify({ text: txBuffer }),
        }),
      ]);
      setJs8Filter({ ...js8Filter, ...filter });
      const refreshed = await api<TxQueueStatus>("/api/js8/tx-queue");
      setTxQueue(refreshed);
    } catch (reason) {
      setJs8Error(errorMessage(reason));
    } finally {
      setJs8AuxSaving(false);
    }
  }

  return (
    <Card className="wide settings-console">
      <header className="settings-page-header">
        <div className="panel-title-with-icon">
          <SettingsIcon size={19} aria-hidden="true" />
          <div>
            <span className="panel-eyebrow">{t("System configuration")}</span>
            <h2>{t("Settings")}</h2>
            <p>{t("Configure JS8Link and the connected JS8Call station.")}</p>
          </div>
        </div>
        <div className={`settings-connection-state ${setup.connected ? "online" : "offline"}`}>
          <Radio size={14} aria-hidden="true" />
          <span>{setup.connected ? t("Verbonden") : t("Niet verbonden")}</span>
        </div>
      </header>
      <Tabs
        value={settingsTab}
        onValueChange={(value) =>
          setSettingsTab(value as "application" | "js8call" | "diagnostics")
        }
      >
        <TabsList>
          <TabsTrigger
            value="application"
            active={settingsTab === "application"}
            onClick={() => setSettingsTab("application")}
          >
            {t("Applicatie")}
          </TabsTrigger>
          <TabsTrigger
            value="js8call"
            active={settingsTab === "js8call"}
            onClick={() => setSettingsTab("js8call")}
          >
            {t("JS8Call")}
          </TabsTrigger>
          <TabsTrigger
            value="diagnostics"
            active={settingsTab === "diagnostics"}
            onClick={() => setSettingsTab("diagnostics")}
          >
            {t("Diagnostiek")}
          </TabsTrigger>
        </TabsList>
      </Tabs>
      {settingsTab === "application" && (
        <div className="settings-workspace">
          <section className="settings-section appearance-section">
            <div className="settings-section-heading">
              <Palette size={17} aria-hidden="true" />
              <div>
                <span className="panel-eyebrow">01 · {t("Interface")}</span>
                <h3>{t("Appearance and language")}</h3>
                <p>{t("Choose how the station console is displayed.")}</p>
              </div>
            </div>
            <div className="settings-field-grid two-column">
              <Label>
                {t("Taal")}
                <select
                  className="select"
                  value={language}
                  onChange={(e) => setLanguage(e.target.value as "nl" | "en")}
                >
                  <option value="nl">{t("Nederlands")}</option>
                  <option value="en">{t("Engels")}</option>
                </select>
              </Label>
              <Label>
                {t("Thema")}
                <select
                  className="select"
                  value={theme}
                  onChange={(e) => setTheme(e.target.value as Theme)}
                >
                  <option value="dark">{t("Donker")}</option>
                  <option value="light">{t("Licht")}</option>
                  <option value="forest">{t("Forest Console")}</option>
                  <option value="field-light">{t("Field Light")}</option>
                  <option value="high-contrast">{t("Hoog contrast")}</option>
                </select>
              </Label>
              <Label>
                {t("Tijdweergave")}
                <select
                  className="select"
                  value={timeDisplay}
                  onChange={(e) => setTimeDisplay(e.target.value as "utc" | "local")}
                >
                  <option value="local">{t("Lokale tijd")}</option>
                  <option value="utc">UTC</option>
                </select>
              </Label>
            </div>
            <div className="settings-subsection-heading">
              <MapPin size={14} aria-hidden="true" />
              <h4>{t("Map settings")}</h4>
            </div>
            <div className="settings-toggle-row">
              <div className="settings-toggle-copy">
                <MapPin size={16} aria-hidden="true" />
                <div>
                  <strong>{t("Kaartpop-ups tonen")}</strong>
                  <span>{t("Toon extra informatie bij hoveren op stations en verbindingen.")}</span>
                </div>
              </div>
              <Switch checked={mapPopups} onCheckedChange={setMapPopups} />
            </div>
            <div className="settings-toggle-row">
              <div className="settings-toggle-copy">
                <Sun size={16} aria-hidden="true" />
                <div>
                  <strong>{t("Greyline tonen")}</strong>
                  <span>{t("Toon de dag-nachtgrens op de Bandmonitor-kaart.")}</span>
                </div>
              </div>
              <Switch checked={mapGreyline} onCheckedChange={setMapGreyline} />
            </div>
            <div className="settings-toggle-row">
              <div className="settings-toggle-copy">
                <Waypoints size={16} aria-hidden="true" />
                <div>
                  <strong>{t("Alleen bidirectionele verbindingen")}</strong>
                  <span>
                    {t(
                      "Toon alleen stations die elkaar wederzijds kunnen ontvangen. Nuttig voor ARQ-communicatie.",
                    )}
                  </span>
                </div>
              </div>
              <Switch checked={mapBidirectionalOnly} onCheckedChange={setMapBidirectionalOnly} />
            </div>
            <div className="settings-toggle-row">
              <div className="settings-toggle-copy">
                <IconChartHistogram size={16} aria-hidden="true" />
                <div>
                  <strong>{t("Stations groeperen")}</strong>
                  <span>
                    {t(
                      "Groepeer nabijgelegen stations op de kaart. Bij uitzoomen worden clusters met aantallen getoond.",
                    )}
                  </span>
                </div>
              </div>
              <Switch checked={mapClusterStations} onCheckedChange={setMapClusterStations} />
            </div>
            <div className="settings-field-grid two-column">
              <Label>
                {t("Meldingstijd ontvangen berichten (seconden)")}
                <Input
                  type="number"
                  min="1"
                  max="60"
                  value={toastDurationSeconds}
                  onChange={(e) => setToastDurationSeconds(Number(e.target.value))}
                />
                <small>
                  {t("Hoe lang een melding zichtbaar blijft. Hoveren pauzeert de aftelling.")}
                </small>
              </Label>
            </div>
          </section>

          <section className="settings-section connection-section">
            <div className="settings-section-heading">
              <ServerCog size={17} aria-hidden="true" />
              <div>
                <span className="panel-eyebrow">02 · {t("Connection")}</span>
                <h3>{t("JS8Link verbinding")}</h3>
                <p>{t("API endpoint and local access control.")}</p>
              </div>
            </div>
            <div className="settings-field-grid two-column">
              <Label>
                {t("JS8Call host")}
                <Input value={host} onChange={(e) => setHost(e.target.value)} />
              </Label>
              <Label>
                {t("JS8Call API-poort")}
                <Input type="number" value={port} onChange={(e) => setPort(e.target.value)} />
              </Label>
            </div>
            <div className="settings-toggle-row">
              <div className="settings-toggle-copy">
                <Shield size={16} aria-hidden="true" />
                <div>
                  <strong>{t("Applicatielogin inschakelen")}</strong>
                  <span>{t("Deze login beveiligt JS8Link, niet de verbinding met JS8Call.")}</span>
                </div>
              </div>
              <Switch checked={authEnabled} onCheckedChange={setAuthEnabled} />
            </div>
            {authEnabled && (
              <div className="settings-field-grid two-column">
                <Label>
                  {t("Gebruikersnaam")}
                  <Input
                    value={username}
                    onChange={(e) => setUsername(e.target.value)}
                    placeholder={t("Laat leeg om te behouden")}
                  />
                </Label>
                <Label>
                  {t("Nieuw wachtwoord")}
                  <Input
                    type="password"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    placeholder={t("Laat leeg om te behouden")}
                  />
                </Label>
              </div>
            )}
            <div className="settings-field-grid two-column retention-row">
              <Label>
                {t("Retentie ontvangen monitorverkeer (dagen)")}
                <Input
                  type="number"
                  min="1"
                  max="3650"
                  value={retentionDays}
                  onChange={(e) => setRetentionDays(Number(e.target.value))}
                />
                <small>{t("Oud monitorverkeer wordt automatisch periodiek verwijderd.")}</small>
              </Label>
              <Label>
                {t("Bandscope tijdsvenster (minuten)")}
                <Input
                  type="number"
                  min="1"
                  max="1440"
                  value={bandScopeMinutes}
                  onChange={(e) => setBandScopeMinutes(e.target.value)}
                  onBlur={() => {
                    setBandScopeMinutes(String(clampBandScopeMinutes(bandScopeMinutes)));
                  }}
                />
                <small>{t("Hoeveel minuten verkeer de bandscope bovenin toont.")}</small>
              </Label>
              <Label>
                {t("Retentie JS8Call API-diagnostiek (dagen)")}
                <Input
                  type="number"
                  min="1"
                  max="365"
                  value={apiMessageRetentionDays}
                  onChange={(e) => setApiMessageRetentionDays(Number(e.target.value))}
                />
                <small>
                  {t(
                    "API-diagnostiek wordt automatisch opgeschoond; BAND_ACTIVITY maximaal 24 uur.",
                  )}
                </small>
              </Label>
              <div className={`connection-readout ${setup.connected ? "online" : "offline"}`}>
                <span>{t("API status")}</span>
                <strong>{setup.connected ? t("Verbonden") : t("Niet verbonden")}</strong>
                <small>
                  {host}:{port}
                </small>
              </div>
            </div>
          </section>

          <section className="settings-section query-section">
            <div className="settings-section-heading">
              <Activity size={17} aria-hidden="true" />
              <div>
                <span className="panel-eyebrow">03 · {t("Station queries")}</span>
                <h3>{t("Station information queries")}</h3>
                <p>
                  {t(
                    "JS8Link asks recently heard stations for additional information. Safe minimums prevent excessive radio time.",
                  )}
                </p>
              </div>
            </div>
            <div className="settings-toggle-row">
              <div className="settings-toggle-copy">
                <Radio size={16} aria-hidden="true" />
                <div>
                  <strong>{t("Automatic station information queries")}</strong>
                  <span>
                    {t("Allow the scheduler to ask stations for SNR, grid and status information.")}
                  </span>
                </div>
              </div>
              <Switch
                checked={querySettings.station_queries_enabled}
                onCheckedChange={(checked) =>
                  setQuerySettings((current) => ({
                    ...current,
                    station_queries_enabled: checked,
                  }))
                }
              />
            </div>
            <div className="settings-field-grid two-column">
              <Label>
                {t("SNR query interval (minutes)")}
                <Input
                  type="number"
                  min="15"
                  max="1440"
                  value={querySettings.query_interval_snr_minutes}
                  onChange={(e) =>
                    setQuerySettings((current) => ({
                      ...current,
                      query_interval_snr_minutes: Number(e.target.value),
                    }))
                  }
                />
              </Label>
              <Label>
                {t("Hearing query interval (minutes)")}
                <Input
                  type="number"
                  min="15"
                  max="1440"
                  value={querySettings.query_interval_hearing_minutes}
                  onChange={(e) =>
                    setQuerySettings((current) => ({
                      ...current,
                      query_interval_hearing_minutes: Number(e.target.value),
                    }))
                  }
                />
              </Label>
              <Label>
                {t("Status query interval (hours)")}
                <Input
                  type="number"
                  min="1"
                  max="168"
                  value={querySettings.query_interval_status_hours}
                  onChange={(e) =>
                    setQuerySettings((current) => ({
                      ...current,
                      query_interval_status_hours: Number(e.target.value),
                    }))
                  }
                />
              </Label>
              <Label>
                {t("Info and grid interval (days)")}
                <Input
                  type="number"
                  min="1"
                  max="365"
                  value={Math.min(
                    querySettings.query_interval_info_days,
                    querySettings.query_interval_grid_days,
                  )}
                  onChange={(e) => {
                    const value = Number(e.target.value);
                    setQuerySettings((current) => ({
                      ...current,
                      query_interval_info_days: value,
                      query_interval_grid_days: value,
                    }));
                  }}
                />
              </Label>
              <Label>
                {t("Maximum queries per hour")}
                <Input
                  type="number"
                  min="1"
                  max="60"
                  value={querySettings.query_max_per_hour}
                  onChange={(e) =>
                    setQuerySettings((current) => ({
                      ...current,
                      query_max_per_hour: Number(e.target.value),
                    }))
                  }
                />
                <small>{t("This budget is spread evenly across the hour.")}</small>
              </Label>
              <Label>
                {t("Minimum spacing (seconds)")}
                <Input
                  type="number"
                  min="60"
                  max="3600"
                  value={querySettings.query_cooldown_seconds}
                  onChange={(e) =>
                    setQuerySettings((current) => ({
                      ...current,
                      query_cooldown_seconds: Number(e.target.value),
                    }))
                  }
                />
                <small>{t("Extra safety interval between station queries.")}</small>
              </Label>
            </div>
          </section>
          <section className="settings-section update-section">
            <div className="settings-section-heading">
              <Download size={17} aria-hidden="true" />
              <div>
                <span className="panel-eyebrow">04 · {t("Maintenance")}</span>
                <h3>{t("Software-updates")}</h3>
                <p>
                  {t(
                    "Updates worden opgehaald uit GitHub Releases. Alpha-updates worden handmatig gedownload en vervangen.",
                  )}
                </p>
              </div>
            </div>
            <div className="settings-field-grid update-grid">
              <Label>
                {t("GitHub-repository")}
                <Input
                  value={updateRepository}
                  readOnly
                  placeholder={t("Geen origin-remote gevonden")}
                />
              </Label>
              <Label>
                {t("Updatebranch")}
                <Input
                  value={updateBranch}
                  onChange={(event) => setUpdateBranch(event.target.value)}
                  placeholder="main"
                />
              </Label>
              <div className="settings-actions">
                <Button
                  disabled={updateChecking || updateApplying}
                  onClick={() => void checkForUpdates()}
                >
                  {updateChecking ? t("Controleren…") : t("Controleren op updates")}
                </Button>
              </div>
            </div>
            {updateInfo && (
              <div className="info-box update-info">
                <strong>
                  {updateInfo.update_available
                    ? t("Er is een update beschikbaar")
                    : t("JS8Link is actueel")}
                </strong>
                <span>
                  {t("Geïnstalleerd")}: {updateInfo.current_commit?.slice(0, 8) || t("Onbekend")} ·{" "}
                  {t("Beschikbaar")}: {updateInfo.latest_commit.slice(0, 8)}
                </span>
                {updateInfo.latest_message && <span>{updateInfo.latest_message}</span>}
                {updateInfo.reason && <span className="warning-text">{t(updateInfo.reason)}</span>}
                {updateInfo.update_available && !updateConfirmation && (
                  <div className="settings-actions">
                    <a
                      className="button primary"
                      href={updateInfo.latest_url}
                      target="_blank"
                      rel="noreferrer"
                    >
                      {t("Open GitHub release")}
                    </a>
                  </div>
                )}
              </div>
            )}
            {updateConfirmation && (
              <div className="info-box update-confirmation">
                <strong>{t("Update nu installeren?")}</strong>
                <span>
                  {t(
                    "Tijdens de update worden dependencies, database-migraties en de frontendbuild bijgewerkt. De applicatie wordt daarna herstart indien mogelijk.",
                  )}
                </span>
                <div className="settings-actions">
                  <Button disabled={updateApplying} onClick={() => setUpdateConfirmation(false)}>
                    {t("Annuleren")}
                  </Button>
                  <Button
                    className="primary"
                    disabled={updateApplying}
                    onClick={() => void applyUpdate()}
                  >
                    {updateApplying ? t("Update installeren…") : t("Bevestigen en installeren")}
                  </Button>
                </div>
              </div>
            )}
            {updateResult && (
              <div className="info-box">
                <strong>{t("Update geïnstalleerd")}</strong>
                <span>
                  {updateResult.restart_scheduled
                    ? t("JS8Link wordt herstart. Deze pagina wordt automatisch opnieuw geladen.")
                    : t("Herstart JS8Link om de backend-update te activeren.")}
                </span>
              </div>
            )}
            {updateError && <div className="error">{updateError}</div>}
          </section>
          <section className="settings-section danger-section">
            <div className="settings-section-heading">
              <Trash2 size={17} aria-hidden="true" />
              <div>
                <span className="panel-eyebrow">05 · {t("Maintenance")}</span>
                <h3>{t("Alle operationele data verwijderen")}</h3>
                <p>
                  {t(
                    "Verwijder ontvangen en verzonden berichten, stations, relaties, queryhistorie en API-diagnostiek. Instellingen blijven behouden.",
                  )}
                </p>
              </div>
            </div>
            {!purgeConfirmation && (
              <div className="settings-actions">
                <Button className="danger" onClick={() => setPurgeConfirmation(true)}>
                  {t("Purge")}
                </Button>
              </div>
            )}
            {purgeConfirmation && (
              <div className="info-box update-confirmation purge-confirmation">
                <strong>{t("Purge nu uitvoeren?")}</strong>
                <span>{t("Deze actie kan niet ongedaan worden gemaakt.")}</span>
                <div className="settings-actions">
                  <Button disabled={purging} onClick={() => setPurgeConfirmation(false)}>
                    {t("Annuleren")}
                  </Button>
                  <Button className="danger" disabled={purging} onClick={() => void purgeData()}>
                    {purging ? t("Bezig met verwijderen…") : t("Data verwijderen")}
                  </Button>
                </div>
              </div>
            )}
            {purgeMessage && <div className="success-text">{purgeMessage}</div>}
          </section>
          {error && <div className="error settings-page-error">{error}</div>}
          <footer className="settings-savebar">
            <div>
              <Database size={15} aria-hidden="true" />
              <span>{t("Changes are stored in the JS8Link database.")}</span>
            </div>
            <Button className="primary" onClick={save} disabled={saving}>
              {saving ? t("Opslaan…") : t("Instellingen opslaan")}
            </Button>
          </footer>
        </div>
      )}
      {settingsTab === "js8call" && (
        <div className="settings-workspace settings-js8-workspace">
          <div className="settings-section-heading js8-settings-heading">
            <Radio size={17} aria-hidden="true" />
            <div>
              <span className="panel-eyebrow">{t("Radio configuration")}</span>
              <h3>{t("JS8Call-instellingen")}</h3>
              <p>
                {t(
                  "Deze instellingen worden rechtstreeks in JS8Call-improved gewijzigd via de API.",
                )}
              </p>
            </div>
          </div>
          {!js8 && !js8Error && (
            <p className="muted">{t("JS8Call-instellingen worden geladen…")}</p>
          )}
          {js8Error && (
            <div className="info-box">
              <strong>{t("JS8Call-instellingen niet beschikbaar")}</strong>
              <span>
                {js8Error}. {t("Controleer of JS8Call verbonden is.")}
              </span>
            </div>
          )}
          {js8 && (
            <div className="settings-fields settings-js8-grid">
              <h4>{t("Station")}</h4>
              <Label>
                Callsign <Input value={js8.callsign} readOnly />
              </Label>
              <Label>
                {t("Grid square")}{" "}
                <Input
                  value={js8.grid}
                  onChange={(e) => setJs8({ ...js8, grid: e.target.value })}
                />
              </Label>
              <Label>
                {t("Station info")}{" "}
                <Input
                  value={js8.info}
                  onChange={(e) => setJs8({ ...js8, info: e.target.value })}
                />
              </Label>
              <Label>
                {t("Station status")}{" "}
                <Input
                  value={js8.status}
                  onChange={(e) => setJs8({ ...js8, status: e.target.value })}
                />
              </Label>
              <h4>{t("Radio en mode")}</h4>
              <Label>
                {t("JS8Call frequency preset")}{" "}
                <select
                  className="select"
                  value={
                    frequencyPresets.some((preset) => preset.dial === js8.dial)
                      ? js8.dial
                      : "custom"
                  }
                  onChange={(e) => {
                    if (e.target.value !== "custom") {
                      setJs8({ ...js8, dial: Number(e.target.value) });
                    }
                  }}
                >
                  <option value="custom">{t("Custom frequency")}</option>
                  {frequencyPresets.map((preset) => (
                    <option key={preset.dial} value={preset.dial}>
                      {preset.label}
                    </option>
                  ))}
                </select>
                <small className="muted">
                  {t("Choose a standard JS8Call frequency or enter one manually below.")}
                </small>
              </Label>
              <Label>
                {t("Dial frequency (Hz)")}{" "}
                <Input
                  type="number"
                  value={js8.dial}
                  onChange={(e) => setJs8({ ...js8, dial: Number(e.target.value) })}
                />
              </Label>
              <Label>
                {t("Offset mode")}{" "}
                <select
                  className="select"
                  value={js8.offset_mode}
                  onChange={(e) =>
                    setJs8({ ...js8, offset_mode: e.target.value as "auto" | "fixed" })
                  }
                >
                  <option value="auto">{t("Auto")}</option>
                  <option value="fixed">{t("Fixed")}</option>
                </select>
              </Label>
              <Label>
                {js8.offset_mode === "auto" ? t("Current offset (Hz)") : t("Fixed offset (Hz)")}{" "}
                <Input
                  type="number"
                  min="1000"
                  max="2500"
                  value={js8.offset_mode === "auto" ? js8.offset : js8.fixed_offset}
                  readOnly={js8.offset_mode === "auto"}
                  onChange={(e) => {
                    const fixedOffset = Number(e.target.value);
                    setJs8({ ...js8, fixed_offset: fixedOffset, offset: fixedOffset });
                  }}
                />
              </Label>
              <Label>
                {t("Transmit speed")}
                <select
                  className="select"
                  value={js8.speed}
                  onChange={(e) => setJs8({ ...js8, speed: Number(e.target.value) })}
                >
                  <option value={0}>Normal</option>
                  <option value={1}>Fast</option>
                  <option value={2}>Turbo</option>
                  <option value={4}>Slow</option>
                  <option value={8}>JS8 60</option>
                </select>
              </Label>
              <h4>{t("Reporting")}</h4>
              <div className="switch-row">
                <Switch
                  checked={js8.spot}
                  onCheckedChange={(checked) => setJs8({ ...js8, spot: checked })}
                />
                <span>{t("Spot reporting inschakelen")}</span>
              </div>
              <div>
                <Button className="primary" onClick={saveJs8} disabled={js8Saving}>
                  {js8Saving ? t("Opslaan…") : t("JS8Call-instellingen opslaan")}
                </Button>
              </div>
              <h4>{t("Bandpass filter")}</h4>
              {js8Filter && (
                <>
                  <Label>
                    {t("Filter center (Hz)")}
                    <Input
                      type="number"
                      min="500"
                      max="2500"
                      value={js8Filter.center ?? 1500}
                      onChange={(event) =>
                        setJs8Filter({ ...js8Filter, center: Number(event.target.value) })
                      }
                    />
                  </Label>
                  <Label>
                    {t("Filter width (Hz)")}
                    <Input
                      type="number"
                      min="50"
                      max="500"
                      value={js8Filter.width ?? 200}
                      onChange={(event) =>
                        setJs8Filter({ ...js8Filter, width: Number(event.target.value) })
                      }
                    />
                  </Label>
                  <div className="settings-toggle-row compact-settings-toggle">
                    <div className="settings-toggle-copy">
                      <Radio size={16} aria-hidden="true" />
                      <div>
                        <strong>{t("Bandpass filter enabled")}</strong>
                        <span>{t("Limit JS8Call reception to the configured passband.")}</span>
                      </div>
                    </div>
                    <Switch
                      checked={js8Filter.enabled ?? true}
                      onCheckedChange={(enabled) => setJs8Filter({ ...js8Filter, enabled })}
                    />
                  </div>
                </>
              )}
              <h4>{t("TX buffer")}</h4>
              <Label>
                {t("Text currently queued in JS8Call")}
                <Textarea value={txBuffer} onChange={(event) => setTxBuffer(event.target.value)} />
                <small>
                  {t(
                    "This changes the JS8Call TX field; it does not start transmission by itself.",
                  )}
                </small>
              </Label>
              <div className="tx-queue-readout">
                <span>{t("TX queue")}</span>
                <strong>{txQueue?.queue_depth ?? 0}</strong>
                <small>
                  {txQueue?.active
                    ? `${t("Active")}: ${txQueue.current_message || t("Unknown")}`
                    : t("No active transmission")}
                </small>
                {txQueue?.active && (
                  <progress value={txQueue.progress_pct} max={100} aria-label={t("TX progress")} />
                )}
              </div>
              <div className="settings-actions">
                <Button
                  className="primary"
                  onClick={() => void saveJs8Auxiliary()}
                  disabled={js8AuxSaving}
                >
                  {js8AuxSaving ? t("Opslaan…") : t("Filter en TX-buffer opslaan")}
                </Button>
              </div>
            </div>
          )}
        </div>
      )}
      {settingsTab === "diagnostics" && (
        <DiagnosticsPanel
          enabled={diagnosticsEnabled}
          retentionDays={diagnosticsRetentionDays}
          onEnabledChange={setDiagnosticsEnabled}
          onRetentionDaysChange={setDiagnosticsRetentionDays}
          onSave={save}
          saving={saving}
        />
      )}
    </Card>
  );
}

function DiagnosticsPanel({
  enabled,
  retentionDays,
  onEnabledChange,
  onRetentionDaysChange,
  onSave,
  saving,
}: {
  enabled: boolean;
  retentionDays: number;
  onEnabledChange: (enabled: boolean) => void;
  onRetentionDaysChange: (days: number) => void;
  onSave: () => Promise<void>;
  saving: boolean;
}) {
  const { t } = useLanguage();
  const { formatDateTime } = useTimeDisplay();
  const [traces, setTraces] = useState<DiagnosticTraceSummary[]>([]);
  const [selected, setSelected] = useState<DiagnosticTraceDetail>();
  const [source, setSource] = useState("");
  const [severity, setSeverity] = useState("");
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [purging, setPurging] = useState(false);

  const loadTraces = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams({ limit: "200" });
      if (source) params.set("source", source);
      if (severity) params.set("severity", severity);
      if (search.trim()) params.set("search", search.trim());
      const result = await api<{ traces: DiagnosticTraceSummary[] }>(
        `/api/diagnostics/traces?${params.toString()}`,
      );
      setTraces(result.traces);
      setError("");
    } catch (reason) {
      setError(errorMessage(reason));
    } finally {
      setLoading(false);
    }
  }, [search, severity, source]);

  useEffect(() => {
    const timer = window.setTimeout(() => void loadTraces(), search ? 250 : 0);
    return () => window.clearTimeout(timer);
  }, [loadTraces, search]);

  useEffect(() => {
    const protocol = window.location.protocol === "https:" ? "wss" : "ws";
    const socket = new WebSocket(`${protocol}://${window.location.host}/api/events`);
    socket.onmessage = (message) => {
      try {
        const event = JSON.parse(message.data) as { event?: string };
        if (event.event === "diagnostics.trace") void loadTraces();
      } catch {
        // Ignore malformed event data; the next refresh restores the timeline.
      }
    };
    return () => socket.close();
  }, [loadTraces]);

  async function selectTrace(trace: DiagnosticTraceSummary) {
    try {
      setSelected(await api<DiagnosticTraceDetail>(`/api/diagnostics/traces/${trace.trace_id}`));
    } catch (reason) {
      setError(errorMessage(reason));
    }
  }

  async function purge() {
    setPurging(true);
    try {
      await api("/api/diagnostics/purge", { method: "POST" });
      setSelected(undefined);
      await loadTraces();
    } catch (reason) {
      setError(errorMessage(reason));
    } finally {
      setPurging(false);
    }
  }

  return (
    <div className="settings-workspace diagnostics-workspace">
      <section className="settings-section diagnostics-controls">
        <div className="settings-section-heading">
          <Activity size={17} aria-hidden="true" />
          <div>
            <span className="panel-eyebrow">01 · {t("Diagnostiek")}</span>
            <h3>{t("Diagnoselogboek")}</h3>
            <p>{t("Analyseer brondata, interpretatie en verwerking van JS8Link-activiteiten.")}</p>
          </div>
        </div>
        <div className="settings-toggle-row">
          <div className="settings-toggle-copy">
            <Database size={16} aria-hidden="true" />
            <div>
              <strong>{t("Diagnostiek vastleggen")}</strong>
              <span>{t("Leg JS8Call-invoer, gebruikersacties en verwerking lokaal vast.")}</span>
            </div>
          </div>
          <Switch checked={enabled} onCheckedChange={onEnabledChange} />
        </div>
        <div className="settings-field-grid two-column">
          <Label>
            {t("Retentie diagnoselogboek (dagen)")}
            <Input
              type="number"
              min="1"
              max="365"
              value={retentionDays}
              onChange={(event) => onRetentionDaysChange(Number(event.target.value))}
            />
            <small>{t("Oudere traces worden ieder uur automatisch verwijderd.")}</small>
          </Label>
        </div>
        <div className="settings-actions diagnostics-actions">
          <Button className="primary" onClick={() => void onSave()} disabled={saving}>
            {saving ? t("Opslaan…") : t("Diagnostiek opslaan")}
          </Button>
          <Button className="danger" onClick={() => void purge()} disabled={purging}>
            {purging ? t("Bezig met verwijderen…") : t("Diagnoselogboek wissen")}
          </Button>
        </div>
      </section>

      <section className="settings-section diagnostics-timeline-section">
        <div className="settings-section-heading">
          <Waypoints size={17} aria-hidden="true" />
          <div>
            <span className="panel-eyebrow">02 · {t("Tijdlijn")}</span>
            <h3>{t("Gebeurtenissen")}</h3>
            <p>
              {t("Nieuwe gebeurtenissen verschijnen automatisch terwijl deze pagina open staat.")}
            </p>
          </div>
        </div>
        <div className="diagnostics-filters">
          <Select
            value={source}
            onChange={(event) => setSource(event.target.value)}
            aria-label={t("Bron")}
          >
            <option value="">{t("Alle bronnen")}</option>
            <option value="js8_api">{t("JS8Call API")}</option>
            <option value="user_action">{t("Gebruikersactie")}</option>
            <option value="automatic_task">{t("Automatische taak")}</option>
          </Select>
          <Select
            value={severity}
            onChange={(event) => setSeverity(event.target.value)}
            aria-label={t("Ernst")}
          >
            <option value="">{t("Alle niveaus")}</option>
            <option value="info">Info</option>
            <option value="warning">{t("Waarschuwing")}</option>
            <option value="error">{t("Fout")}</option>
          </Select>
          <Input
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder={t("Zoek in interpretatie of type…")}
          />
          <Button onClick={() => void loadTraces()}>{t("Vernieuwen")}</Button>
        </div>
        <div className="diagnostics-content">
          <div className="diagnostics-timeline" role="list">
            {loading && <p className="muted">{t("Diagnostiek laden…")}</p>}
            {!loading && traces.length === 0 && (
              <p className="muted">{t("Nog geen diagnosegegevens vastgelegd.")}</p>
            )}
            {traces.map((trace) => (
              <button
                type="button"
                role="listitem"
                key={trace.trace_id}
                className={`diagnostic-trace ${selected?.trace_id === trace.trace_id ? "selected" : ""}`}
                onClick={() => void selectTrace(trace)}
              >
                <span className={`diagnostic-severity ${trace.severity}`} aria-hidden="true" />
                <span className="diagnostic-trace-copy">
                  <strong>{trace.summary}</strong>
                  <span>{trace.interpretation}</span>
                </span>
                <time>{trace.created_at ? formatDateTime(trace.created_at) : "—"}</time>
              </button>
            ))}
          </div>
          <aside className="diagnostic-inspector">
            {!selected && (
              <p className="muted">{t("Selecteer een gebeurtenis voor alle drie de lagen.")}</p>
            )}
            {selected && (
              <>
                <div className="diagnostic-layer raw">
                  <span className="panel-eyebrow">01 · {t("Ruwe data")}</span>
                  <pre>{selected.raw_payload || t("Geen ruwe gegevens beschikbaar.")}</pre>
                </div>
                <div className="diagnostic-layer interpretation">
                  <span className="panel-eyebrow">02 · {t("Interpretatie")}</span>
                  <p>{selected.interpretation}</p>
                </div>
                <div className="diagnostic-layer processing">
                  <span className="panel-eyebrow">03 · {t("Verwerking")}</span>
                  {selected.processing.length === 0 && (
                    <p>{t("Nog geen verwerkingsstappen vastgelegd.")}</p>
                  )}
                  {selected.processing.map((step) => (
                    <div className="diagnostic-processing-step" key={step.id}>
                      <strong>{step.operation}</strong>
                      <span className={step.outcome}>{step.detail}</span>
                      {step.payload && <pre>{step.payload}</pre>}
                    </div>
                  ))}
                </div>
              </>
            )}
          </aside>
        </div>
        {error && <div className="error diagnostics-error">{error}</div>}
      </section>
    </div>
  );
}

function BandScope({
  signals,
  activeOffset,
  band,
  onOffsetSelect,
}: {
  signals: SpectrumSignal[];
  activeOffset?: number;
  band?: string;
  onOffsetSelect?: (offset: number) => void;
}) {
  const { theme } = useTheme();
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const handleCanvasClick = (event: React.MouseEvent<HTMLCanvasElement>) => {
    if (!onOffsetSelect || !canvasRef.current) return;
    const rect = canvasRef.current.getBoundingClientRect();
    const left = 36;
    const right = 12;
    const plotWidth = Math.max(1, rect.width - left - right);
    const xPos = event.clientX - rect.left - left;
    if (xPos < 0 || xPos > plotWidth) return;
    const offset = 500 + (xPos / plotWidth) * 2000;
    // Snap to 10 Hz and clamp to the valid JS8 offset range.
    const snapped = Math.round(offset / 10) * 10;
    onOffsetSelect(Math.min(2500, Math.max(1000, snapped)));
  };
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const draw = () => {
      const bounds = canvas.getBoundingClientRect();
      const scale = window.devicePixelRatio || 1;
      canvas.width = Math.max(1, Math.round(bounds.width * scale));
      canvas.height = Math.max(1, Math.round(bounds.height * scale));
      const context = canvas.getContext("2d");
      if (!context) return;
      context.scale(scale, scale);
      const width = bounds.width;
      const height = bounds.height;
      const left = 36;
      const right = 12;
      const top = 5;
      const baseline = height - 13;
      const plotWidth = Math.max(1, width - left - right);
      const x = (offset: number) => left + ((offset - 500) / 2000) * plotWidth;
      const styles = getComputedStyle(document.documentElement);
      const token = (name: string, fallback: string) =>
        styles.getPropertyValue(name).trim() || fallback;
      const palette = {
        background: token("--console-panel", "#0c1015"),
        line: token("--console-line", "#252e38"),
        text: token("--console-muted", "#8f9aa7"),
        rx: token("--console-rx", "#3f96f6"),
        tx: token("--console-tx", "#f39a18"),
        good: token("--console-ok", "#68c779"),
        poor: token("--console-danger", "#f06464"),
        hb: token("--scope-hb", "#102019"),
        normal: token("--scope-normal", "#0e1722"),
      };
      context.fillStyle = palette.background;
      context.fillRect(0, 0, width, height);
      context.fillStyle = palette.hb;
      context.fillRect(x(500), top, x(1000) - x(500), baseline - top);
      context.fillStyle = palette.normal;
      context.fillRect(x(1000), top, x(2500) - x(1000), baseline - top);
      context.strokeStyle = palette.line;
      context.lineWidth = 1;
      context.beginPath();
      context.moveTo(left, baseline + 0.5);
      context.lineTo(width - right, baseline + 0.5);
      context.stroke();
      context.font = '500 8px "IBM Plex Mono"';
      context.textAlign = "center";
      context.fillStyle = palette.text;
      for (const tick of [500, 1000, 1500, 2000, 2500]) {
        const tickX = x(tick);
        context.beginPath();
        context.moveTo(tickX + 0.5, baseline - 3);
        context.lineTo(tickX + 0.5, baseline + 3);
        context.stroke();
        context.fillText(String(tick), tickX, height - 2);
      }
      context.textAlign = "left";
      context.fillText("HB", x(520), 11);
      context.fillText("JS8 PASSBAND", x(1020), 11);
      for (const signal of signals) {
        const signalX = x(signal.offset);
        const strength = typeof signal.snr === "number" ? signal.snr : -12;
        const barHeight = Math.max(5, Math.min(21, 10 + (strength + 20) * 0.42));
        context.strokeStyle = signal.direction === "tx" ? palette.tx : palette.rx;
        context.lineWidth = signal.direction === "tx" ? 3 : 2;
        context.beginPath();
        context.moveTo(signalX, baseline - 1);
        context.lineTo(signalX, baseline - barHeight);
        context.stroke();
      }
      if (activeOffset !== undefined) {
        const markerX = x(activeOffset);
        context.strokeStyle = palette.tx;
        context.lineWidth = 1;
        context.setLineDash([2, 2]);
        context.beginPath();
        context.moveTo(markerX, top);
        context.lineTo(markerX, baseline);
        context.stroke();
        context.setLineDash([]);
        context.fillStyle = palette.tx;
        context.beginPath();
        context.moveTo(markerX - 4, top);
        context.lineTo(markerX + 4, top);
        context.lineTo(markerX, top + 5);
        context.closePath();
        context.fill();
      }
    };
    draw();
    const observer = new ResizeObserver(draw);
    observer.observe(canvas);
    return () => observer.disconnect();
  }, [activeOffset, signals, theme]);
  return (
    <section className="band-scope" aria-label={`Band activity ${band || ""}`}>
      <div className="band-scope-label">
        <IconWaveSine size={15} aria-hidden="true" />
        <div>
          <span>BAND SCOPE</span>
          <strong>{band || "--"}</strong>
        </div>
      </div>
      <canvas
        ref={canvasRef}
        role="img"
        aria-label={`${signals.length} active offsets`}
        onClick={handleCanvasClick}
        className={onOffsetSelect ? "band-scope-canvas interactive" : "band-scope-canvas"}
      />
      <div className="band-scope-legend" aria-hidden="true">
        <span className="rx">
          <IconArrowDownLeft size={12} /> RX
        </span>
        <span className="tx">
          <IconArrowUpRight size={12} /> TX
        </span>
      </div>
    </section>
  );
}

export function App() {
  const { t } = useLanguage();
  const { timeDisplay, formatUtcClock, formatDisplayClock } = useTimeDisplay();
  const [setup, setSetup] = useState<Setup>();
  const [status, setStatus] = useState<Status>();
  const [error, setError] = useState("");
  const [needsLogin, setNeedsLogin] = useState(false);
  const [radioActivity, setRadioActivity] = useState<"idle" | "rx" | "tx">("idle");
  const [selectedCallsign, setSelectedCallsign] = useState<string>();
  const [incomingToast, setIncomingToast] = useState<IncomingToast>();
  const [toastDurationSeconds, setToastDurationSeconds] = useState(5);
  const [tuning, setTuning] = useState(false);
  const [activeMenu, setActiveMenu] = useState<MenuItem>("chat");
  const [clockNow, setClockNow] = useState(() => new Date());
  const [frequencyPresets, setFrequencyPresets] = useState<FrequencyPreset[]>([]);
  const [optimisticDial, setOptimisticDial] = useState<number>();
  const [setupLoading, setSetupLoading] = useState(true);
  const [appVersion, setAppVersion] = useState("");
  const [headerUpdate, setHeaderUpdate] = useState<UpdateInfo>();
  const [headerUpdateOpen, setHeaderUpdateOpen] = useState(false);
  const [headerUpdateApplying, setHeaderUpdateApplying] = useState(false);
  const [headerUpdateReloading, setHeaderUpdateReloading] = useState(false);
  const [headerUpdateError, setHeaderUpdateError] = useState("");
  const [changelogOpen, setChangelogOpen] = useState(false);
  const [changelogLoading, setChangelogLoading] = useState(false);
  const [changelogReleases, setChangelogReleases] = useState<ChangelogRelease[]>([]);
  const [changelogError, setChangelogError] = useState("");
  const [helpOpen, setHelpOpen] = useState(false);
  const [helpTopic, setHelpTopic] = useState("global");
  const [spectrumSignals, setSpectrumSignals] = useState<SpectrumSignal[]>([]);
  const [monitorHistoryMinutes, setMonitorHistoryMinutes] = useState(1440);
  const [offsetPopupOpen, setOffsetPopupOpen] = useState(false);
  const [offsetInput, setOffsetInput] = useState("");
  const [offsetModeDraft, setOffsetModeDraft] = useState<"auto" | "fixed">("auto");
  const [pendingOffset, setPendingOffset] = useState<number>();
  const offsetButtonRef = useRef<HTMLButtonElement>(null);
  const [offsetPopoverPosition, setOffsetPopoverPosition] = useState({ top: 0, left: 0 });
  const activityTimer = useRef<number | null>(null);
  const dismissToast = useCallback(() => setIncomingToast(undefined), []);
  const openHelp = useCallback((topic: string) => {
    setHelpTopic(topic);
    setHelpOpen(true);
  }, []);
  const loadSelectedCallsign = useCallback(async () => {
    try {
      const result = await api<{ callsign: string | null }>("/api/js8/call-selected");
      setSelectedCallsign(result.callsign || undefined);
    } catch {
      setSelectedCallsign(undefined);
    }
  }, []);
  async function load() {
    setSetupLoading(true);
    try {
      const s = await api<Setup>("/api/setup/status");
      setSetup(s);
      if (s.setup_complete && s.connected) {
        try {
          const nextStatus = await api<Status>("/api/status");
          setStatus(nextStatus);
          setOptimisticDial((current) =>
            current !== undefined &&
            (nextStatus.frequency?.params?.DIAL ?? nextStatus.dial) === current
              ? undefined
              : current,
          );
          setNeedsLogin(false);
        } catch (e) {
          if (s.auth_enabled && String(e).includes("401")) setNeedsLogin(true);
          else throw e;
        }
      }
    } catch (e) {
      setError(String(e));
    } finally {
      setSetupLoading(false);
    }
  }
  useEffect(() => {
    void load();
  }, []);
  useEffect(() => {
    void api<{ version: string }>("/api/health")
      .then((health) => setAppVersion(health.version))
      .catch(() => undefined);
  }, []);
  useEffect(() => {
    if (!setup?.setup_complete) return;
    let active = true;
    async function checkForUpdate() {
      try {
        const result = await api<UpdateInfo>("/api/update/check");
        if (active) setHeaderUpdate(result);
      } catch {
        // Development checkouts may not have an origin remote. Keep the header quiet in that case.
      }
    }
    void checkForUpdate();
    const startupRetry = window.setTimeout(() => void checkForUpdate(), 5 * 60 * 1000);
    const timer = window.setInterval(() => void checkForUpdate(), 6 * 60 * 60 * 1000);
    return () => {
      active = false;
      window.clearTimeout(startupRetry);
      window.clearInterval(timer);
    };
  }, [setup?.setup_complete]);
  useEffect(() => {
    if (!setup?.setup_complete || !status?.connected) return;
    void loadSelectedCallsign();
    const timer = window.setInterval(() => void loadSelectedCallsign(), 30_000);
    return () => window.clearInterval(timer);
  }, [loadSelectedCallsign, setup?.setup_complete, status?.connected]);
  useEffect(() => {
    if (!setup?.setup_complete) return;
    void api<FrequencyPreset[]>("/api/js8/frequency-presets")
      .then(setFrequencyPresets)
      .catch((reason) => setError(String(reason)));
  }, [setup?.setup_complete]);
  const currentBand = status?.band;
  const loadSpectrum = useCallback(async () => {
    try {
      const query = new URLSearchParams({ minutes: String(monitorHistoryMinutes) });
      if (currentBand) query.set("band", currentBand);
      const result = await api<{ signals: SpectrumSignal[] }>(`/api/monitor/spectrum?${query}`);
      setSpectrumSignals(result.signals);
    } catch {
      setSpectrumSignals([]);
    }
  }, [currentBand, monitorHistoryMinutes]);
  useEffect(() => {
    if (!setup?.setup_complete) return;
    void api<{ history_minutes?: number; toast_duration_seconds?: number }>("/api/preferences")
      .then((preference) => {
        if (preference.history_minutes) setMonitorHistoryMinutes(preference.history_minutes);
        if (preference.toast_duration_seconds) {
          setToastDurationSeconds(preference.toast_duration_seconds);
        }
      })
      .catch(() => undefined);
    void loadSpectrum();
    const timer = window.setInterval(() => void loadSpectrum(), 60_000);
    return () => window.clearInterval(timer);
  }, [loadSpectrum, setup?.setup_complete]);
  useEffect(() => {
    if (!setup?.setup_complete) return;
    const protocol = location.protocol === "https:" ? "wss" : "ws";
    const socket = new WebSocket(`${protocol}://${location.host}/api/events`);
    socket.onmessage = (event) => {
      try {
        const payload = JSON.parse(event.data) as {
          event?: string;
          data?: {
            ptt?: boolean;
            callsign?: string;
            text?: string;
            intended_for_local?: boolean;
            duplicate?: boolean;
          };
        };
        const eventName = payload.event?.toLowerCase() ?? "";
        if (
          eventName === "chat.message.received" &&
          payload.data?.intended_for_local &&
          !payload.data.duplicate &&
          payload.data.callsign &&
          payload.data.text
        ) {
          setIncomingToast({
            id: Date.now(),
            callsign: payload.data.callsign,
            text: payload.data.text,
          });
        }
        // RX activity: something was decoded/received on the band.
        const rxEvents = ["radio.rx", "activity.received", "chat.message.received", "radio.spot"];
        // TX activity: something is being transmitted.
        const txEvents = ["tx.progress", "radio.tx_frame", "chat.message.sent"];
        let activity: "rx" | "tx" | undefined;
        if (rxEvents.includes(eventName)) {
          activity = "rx";
        } else if (txEvents.includes(eventName)) {
          activity = "tx";
        }
        // PTT on → TX lit, kept alive by incoming TX_FRAME events.
        if (eventName === "radio.ptt" && payload.data?.ptt) {
          activity = "tx";
        }
        if (activity) {
          setRadioActivity(activity);
          if (activityTimer.current) window.clearTimeout(activityTimer.current);
          activityTimer.current = window.setTimeout(() => {
            setRadioActivity("idle");
            activityTimer.current = null;
          }, 3000);
        }

        // Only reload full status on connection / state-change events.
        const stateEvents = new Set([
          "connection.reconnected",
          "radio.ptt",
          "js8call.closing",
          "js8call.error",
        ]);
        if (stateEvents.has(eventName)) {
          void load();
        }
        // Spectrum only reloads on new activity or periodic timer.
        if (rxEvents.includes(eventName) || eventName === "radio.ptt") {
          void loadSpectrum();
        }
      } catch {
        // Ignore malformed event envelopes; the connection indicator remains unchanged.
      }
    };
    // Periodic fallback: ensure status stays in sync even if events are missed.
    const statusTimer = window.setInterval(() => {
      void load();
      void loadSpectrum();
    }, 30_000);
    return () => {
      socket.close();
      if (activityTimer.current) window.clearTimeout(activityTimer.current);
      window.clearInterval(statusTimer);
    };
  }, [loadSpectrum, setup?.setup_complete]);
  useEffect(() => {
    const timer = window.setInterval(() => {
      setClockNow(new Date());
    }, 1000);
    return () => window.clearInterval(timer);
  }, []);
  const frequency = status?.frequency?.params ?? {
    DIAL: status?.dial ?? undefined,
    OFFSET: status?.offset ?? undefined,
  };
  const displayFrequency =
    optimisticDial === undefined ? frequency : { ...frequency, DIAL: optimisticDial };
  const radioDial = displayFrequency?.DIAL || displayFrequency?.FREQ;
  const selectedPreset = frequencyPresets.find((preset) => preset.dial === radioDial);
  if (!setup) {
    return (
      <main className="shell">
        <Card>
          <h2>{t("JS8Link verbinding")}</h2>
          <p className="error">{setupLoading ? t("Applicatie laden…") : error}</p>
          {!setupLoading && <Button onClick={() => void load()}>{t("Opnieuw proberen")}</Button>}
        </Card>
      </main>
    );
  }
  if (!setup.setup_complete) return <SetupWizard onDone={() => void load()} />;
  if (needsLogin) return <Login onDone={() => void load()} />;
  async function changeBand(dial: number) {
    try {
      await api("/api/rig/frequency", {
        method: "POST",
        body: JSON.stringify({ dial, offset: status?.normal_offset ?? 1500 }),
      });
      const offset = status?.normal_offset ?? 1500;
      setOptimisticDial(dial);
      setStatus((previous) =>
        previous
          ? {
              ...previous,
              dial,
              offset,
              frequency: {
                ...previous.frequency,
                params: {
                  ...previous.frequency?.params,
                  DIAL: dial,
                  OFFSET: offset,
                },
              },
              band: frequencyPresets.find((preset) => preset.dial === dial)?.band,
            }
          : previous,
      );
    } catch (e) {
      setError(String(e));
    }
  }
  async function changeSpeed(nextSpeed: number) {
    try {
      await api("/api/mode/speed", { method: "POST", body: JSON.stringify({ speed: nextSpeed }) });
      await load();
    } catch (e) {
      setError(String(e));
    }
  }
  async function applyOffset(nextOffset: number) {
    setError("");
    try {
      await api("/api/js8/settings", {
        method: "PATCH",
        body: JSON.stringify({
          offset: nextOffset,
          offset_mode: "fixed",
          fixed_offset: nextOffset,
        }),
      });
      setOffsetPopupOpen(false);
      setOffsetInput("");
      await load();
    } catch (e) {
      setError(String(e));
    }
  }
  async function setOffsetAuto() {
    setError("");
    try {
      await api("/api/js8/settings", {
        method: "PATCH",
        body: JSON.stringify({ offset_mode: "auto" }),
      });
      setOffsetPopupOpen(false);
      await load();
    } catch (e) {
      setError(String(e));
    }
  }
  function toggleOffsetPopup() {
    if (offsetPopupOpen) {
      setOffsetPopupOpen(false);
      return;
    }
    const button = offsetButtonRef.current;
    if (button) {
      const rect = button.getBoundingClientRect();
      const width = 220;
      setOffsetPopoverPosition({
        top: rect.bottom + 6,
        left: Math.max(8, Math.min(rect.right - width, window.innerWidth - width - 8)),
      });
    }
    setOffsetModeDraft(status?.offset_mode === "fixed" ? "fixed" : "auto");
    setOffsetInput(
      status?.offset_mode === "fixed"
        ? String(status?.normal_offset ?? displayFrequency?.OFFSET ?? 1500)
        : "",
    );
    setOffsetPopupOpen(true);
  }
  function handleOffsetSelect(offset: number) {
    if (status?.offset_mode === "auto") {
      setPendingOffset(offset); // Ask before switching from auto to manual.
    } else {
      void applyOffset(offset);
    }
  }
  async function toggleRx() {
    setError("");
    try {
      await api("/api/js8/rx-toggle", {
        method: "POST",
        body: JSON.stringify({ enabled: !status?.rx_enabled }),
      });
      await load();
    } catch (e) {
      setError(String(e));
    }
  }
  async function toggleTx() {
    setError("");
    try {
      await api("/api/js8/tx-toggle", {
        method: "POST",
        body: JSON.stringify({ enabled: !status?.tx_enabled }),
      });
      await load();
    } catch (e) {
      setError(String(e));
    }
  }
  async function setTune(enabled: boolean) {
    setError("");
    setTuning(enabled);
    try {
      await api("/api/js8/tune", {
        method: "POST",
        body: JSON.stringify({ enabled }),
      });
    } catch (e) {
      setTuning(false);
      setError(String(e));
    }
  }
  async function clearSelectedCallsign() {
    setError("");
    try {
      await api("/api/js8/call-selected/clear", { method: "POST" });
      setSelectedCallsign(undefined);
    } catch (e) {
      setError(String(e));
    }
  }
  async function applyHeaderUpdate() {
    setHeaderUpdateApplying(true);
    setHeaderUpdateError("");
    try {
      const result = await api<UpdateResult>("/api/update/apply", { method: "POST" });
      if (result.status === "current") {
        setHeaderUpdate((current) => (current ? { ...current, update_available: false } : current));
        setHeaderUpdateOpen(false);
        return;
      }
      setHeaderUpdateReloading(true);
      window.setTimeout(() => window.location.reload(), result.restart_scheduled ? 8000 : 1200);
    } catch (reason) {
      setHeaderUpdateError(errorMessage(reason));
    } finally {
      setHeaderUpdateApplying(false);
    }
  }
  async function openChangelog() {
    setChangelogOpen(true);
    setChangelogLoading(true);
    setChangelogError("");
    try {
      const result = await api<{ releases: ChangelogRelease[] }>("/api/changelog");
      setChangelogReleases(result.releases);
    } catch (reason) {
      setChangelogError(errorMessage(reason));
    } finally {
      setChangelogLoading(false);
    }
  }
  const speed = status?.mode?.params?.SPEED ?? status?.speed ?? undefined;
  const menuItems = [
    { id: "chat" as const, label: t("Chat"), icon: IconMessage },
    { id: "messages" as const, label: t("Messages"), icon: IconMail },
    { id: "monitor" as const, label: t("Monitor"), icon: IconChartHistogram },
  ];
  return (
    <div className="app">
      {incomingToast && (
        <IncomingMessageToast
          toast={incomingToast}
          durationSeconds={toastDurationSeconds}
          onDismiss={dismissToast}
        />
      )}
      <main className="shell">
        <header className="topbar">
          <div className="station-brand">
            <IconAntennaBars5 size={27} stroke={1.7} aria-hidden="true" />
            <div>
              <div className="brand">JS8Link</div>
              <div className="station-brand-meta">
                <strong>{status?.station?.value || status?.callsign || "NO CALL"}</strong>
                <button className="current-version-link" onClick={() => void openChangelog()}>
                  v{appVersion || "…"}
                </button>
                {headerUpdate?.update_available && (
                  <button
                    className="update-available-link"
                    onClick={() => {
                      setHeaderUpdateError("");
                      setHeaderUpdateOpen(true);
                    }}
                  >
                    {t("Update beschikbaar")}
                  </button>
                )}
              </div>
            </div>
          </div>
          <nav className="main-menu" aria-label="Hoofdmenu">
            {menuItems.map(({ id, label, icon: MenuIcon }) => (
              <button
                className={`menu-item ${activeMenu === id ? "active" : ""}`}
                key={id}
                onClick={() => setActiveMenu(id)}
              >
                <MenuIcon size={19} stroke={1.6} aria-hidden="true" />
                <span>{label}</span>
              </button>
            ))}
          </nav>
          <div className="header-actions" aria-label={t("Radio en mode")}>
            <div className="station-instrument vfo-instrument">
              <span className="instrument-label">VFO A</span>
              <strong className="vfo-frequency">{formatDialFrequency(radioDial)}</strong>
            </div>
            <label className="station-instrument band-instrument">
              <span className="instrument-label">{t("Band")}</span>
              <select
                className="instrument-select"
                aria-label={t("Band")}
                value={selectedPreset?.dial ?? "custom"}
                disabled={!status?.connected}
                onChange={(event) => {
                  if (event.target.value !== "custom") void changeBand(Number(event.target.value));
                }}
              >
                <option value="custom">{selectedPreset?.band || t("Custom")}</option>
                {frequencyPresets.map((preset) => (
                  <option key={preset.dial} value={preset.dial}>
                    {preset.band}
                  </option>
                ))}
              </select>
            </label>
            <label className="station-instrument mode-instrument">
              <span className="instrument-label">{t("Mode")} / SPEED</span>
              <span className="mode-value">
                <strong>JS8</strong>
                <b>{speedLabel(speed)}</b>
              </span>
              <select
                className="instrument-select speed-select"
                aria-label={t("Transmit speed")}
                value={speed ?? ""}
                disabled={!status?.connected}
                onChange={(event) => void changeSpeed(Number(event.target.value))}
              >
                <option value="">--</option>
                <option value={0}>NORMAL</option>
                <option value={1}>FAST</option>
                <option value={2}>TURBO</option>
                <option value={4}>SLOW</option>
                <option value={8}>JS8 60</option>
              </select>
            </label>
            <div className="station-instrument offset-instrument" aria-live="polite">
              <button
                type="button"
                ref={offsetButtonRef}
                className="offset-instrument-button"
                aria-haspopup="dialog"
                aria-expanded={offsetPopupOpen}
                aria-label={t("Offset instellen")}
                title={t("Offset instellen")}
                onClick={toggleOffsetPopup}
              >
                <span className="instrument-label">{t("Offset")}</span>
                <strong>{formatOffset(status?.normal_offset ?? displayFrequency?.OFFSET)}</strong>
                <span className="offset-button-footer">
                  <span className="instrument-secondary">
                    {status?.offset_mode === "auto" ? t("Auto") : t("Fixed")}
                  </span>
                  <ChevronDown className="offset-button-chevron" size={11} aria-hidden="true" />
                </span>
              </button>
              {offsetPopupOpen &&
                createPortal(
                  <>
                    <div className="popover-backdrop" onClick={() => setOffsetPopupOpen(false)} />
                    <div
                      className="offset-popover"
                      role="dialog"
                      aria-label={t("Offset instellen")}
                      style={{ top: offsetPopoverPosition.top, left: offsetPopoverPosition.left }}
                    >
                      <span className="instrument-label">{t("Offset instellen")}</span>
                      <div className="offset-mode-row">
                        <button
                          type="button"
                          className={`offset-mode-choice ${offsetModeDraft === "auto" ? "active" : ""}`}
                          onClick={() => void setOffsetAuto()}
                        >
                          {t("Auto")}
                        </button>
                        <button
                          type="button"
                          className={`offset-mode-choice ${offsetModeDraft === "fixed" ? "active" : ""}`}
                          onClick={() => {
                            setOffsetModeDraft("fixed");
                            setOffsetInput(
                              String(status?.normal_offset ?? displayFrequency?.OFFSET ?? 1500),
                            );
                          }}
                        >
                          {t("Handmatig")}
                        </button>
                      </div>
                      <Input
                        className="offset-popover-input"
                        type="number"
                        min="1000"
                        max="2500"
                        step="10"
                        placeholder="1500"
                        value={offsetInput}
                        disabled={offsetModeDraft !== "fixed"}
                        onChange={(e) => setOffsetInput(e.target.value)}
                      />
                      <Button
                        className="offset-popover-apply"
                        disabled={offsetModeDraft !== "fixed" || !offsetInput}
                        onClick={() => {
                          const parsed = parseInt(offsetInput, 10);
                          if (Number.isFinite(parsed)) {
                            void applyOffset(Math.min(2500, Math.max(1000, parsed)));
                          }
                        }}
                      >
                        {t("Toepassen")}
                      </Button>
                    </div>
                  </>,
                  document.body,
                )}
            </div>
            <div className="station-instrument selected-call-instrument">
              <span className="instrument-label">{t("Geselecteerd")}</span>
              <div className="selected-call-value">
                <strong>{selectedCallsign || t("Geen selectie")}</strong>
                {selectedCallsign && (
                  <button
                    type="button"
                    className="selected-call-clear"
                    aria-label={t("Selectie wissen")}
                    title={t("Selectie wissen")}
                    onClick={() => void clearSelectedCallsign()}
                  >
                    ×
                  </button>
                )}
              </div>
            </div>
            <button
              className={`station-instrument trx-instrument rx ${radioActivity === "rx" ? "live" : ""} ${status?.rx_enabled === false ? "disabled" : "enabled"}`}
              aria-pressed={status?.rx_enabled !== false}
              title={
                status?.rx_enabled === false
                  ? t("RX lokaal inschakelen")
                  : t("RX lokaal uitschakelen")
              }
              onClick={() => void toggleRx()}
            >
              <IconArrowDownLeft size={17} stroke={1.8} aria-hidden="true" />
              <strong>RX</strong>
            </button>
            <button
              className={`station-instrument trx-instrument tune ${tuning ? "active" : ""}`}
              aria-pressed={tuning}
              title={t("Ingedrukt houden om te tunen")}
              onPointerDown={(event) => {
                event.currentTarget.setPointerCapture(event.pointerId);
                void setTune(true);
              }}
              onPointerUp={() => void setTune(false)}
              onPointerCancel={() => void setTune(false)}
              onKeyDown={(event) => {
                if ((event.key === "Enter" || event.key === " ") && !tuning) {
                  event.preventDefault();
                  void setTune(true);
                }
              }}
              onKeyUp={(event) => {
                if (event.key === "Enter" || event.key === " ") {
                  event.preventDefault();
                  void setTune(false);
                }
              }}
              onBlur={() => {
                if (tuning) void setTune(false);
              }}
            >
              <IconAntennaBars5 size={17} stroke={1.8} aria-hidden="true" />
              <strong>TUNE</strong>
            </button>
            <button
              className={`station-instrument trx-instrument tx ${radioActivity === "tx" ? "live" : ""} ${status?.tx_enabled === false ? "disabled" : "enabled"}`}
              aria-pressed={status?.tx_enabled !== false}
              title={
                status?.tx_enabled === false
                  ? t("TX lokaal toestaan")
                  : t("TX lokaal blokkeren en lopende TX stoppen")
              }
              onClick={() => void toggleTx()}
            >
              <IconArrowUpRight size={17} stroke={1.8} aria-hidden="true" />
              <strong>TX</strong>
              <span>{status?.queue?.params?.DEPTH ?? status?.tx_queue_depth ?? 0}</span>
            </button>
            <div className="station-instrument connection-instrument">
              <IconRadio
                className={`connection-icon ${status?.connected ? "online" : ""}`}
                size={18}
                stroke={1.8}
                aria-hidden="true"
              />
              <div>
                <strong>{status?.connected ? "JS8CALL" : t("Niet verbonden")}</strong>
                <span>{status?.connected ? t("Verbonden") : setup.host}</span>
              </div>
            </div>
            <div
              className={`station-instrument time-instrument ${timeDisplay === "utc" ? "time-single" : "time-dual"}`}
            >
              {timeDisplay === "utc" ? (
                <>
                  <span className="instrument-label">
                    <IconClock size={11} /> UTC
                  </span>
                  <time>{formatUtcClock(clockNow)}</time>
                </>
              ) : (
                <>
                  <div className="time-line">
                    <span className="instrument-label">{t("Lokaal")}</span>
                    <time>{formatDisplayClock(clockNow)}</time>
                  </div>
                  <div className="time-line utc-time-line">
                    <span className="instrument-label">
                      <IconClock size={11} /> UTC
                    </span>
                    <time>{formatUtcClock(clockNow)}</time>
                  </div>
                </>
              )}
            </div>
            <button
              className={`icon-menu-item settings-menu-item ${activeMenu === "settings" ? "active" : ""}`}
              aria-label={t("Settings")}
              title={t("Settings")}
              onClick={() => setActiveMenu("settings")}
            >
              <IconSettings size={20} stroke={1.6} aria-hidden="true" />
              <span>{t("Settings")}</span>
            </button>
            <HelpButton label={t("Help")} showText onClick={() => openHelp(activeMenu)} />
          </div>
        </header>
        <BandScope
          signals={spectrumSignals}
          activeOffset={status?.normal_offset ?? displayFrequency?.OFFSET}
          band={selectedPreset?.band || status?.band}
          onOffsetSelect={handleOffsetSelect}
        />
        {error && <div className="error card">{error}</div>}
        <div className="grid">
          {activeMenu === "settings" && <SettingsPanel setup={setup} onSaved={() => void load()} />}
          {activeMenu === "messages" && <MessagesPanel />}
          {activeMenu === "monitor" && (
            <MonitorPanel
              localCallsign={status?.callsign ?? status?.station?.value}
              onHistoryMinutesChange={setMonitorHistoryMinutes}
            />
          )}
          {activeMenu === "chat" && (
            <ChatPanel
              connected={Boolean(status?.connected)}
              speed={speed}
              onSpeedChange={changeSpeed}
            />
          )}
        </div>
      </main>
      <HelpDrawer open={helpOpen} topicId={helpTopic} onClose={() => setHelpOpen(false)} />
      {pendingOffset !== undefined && (
        <div
          className="modal-backdrop"
          role="presentation"
          onMouseDown={(event) => {
            if (event.target === event.currentTarget) setPendingOffset(undefined);
          }}
        >
          <section
            className="modal-card confirm-offset-modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="offset-confirm-title"
          >
            <header className="modal-header">
              <div>
                <h2 id="offset-confirm-title">{t("Offset handmatig instellen")}</h2>
                <p className="muted">{t("De offset staat momenteel op automatisch.")}</p>
              </div>
              <Button
                className="modal-close"
                aria-label={t("Sluiten")}
                onClick={() => setPendingOffset(undefined)}
              >
                <X size={18} aria-hidden="true" />
              </Button>
            </header>
            <div className="stack">
              <p>
                {t("Wil je de offset handmatig op")}{" "}
                <strong className="offset-confirm-value">{formatOffset(pendingOffset)}</strong>{" "}
                {t("zetten?")}
              </p>
              <p className="muted">
                {t("Je kunt de offset altijd via de offsetknop terugzetten op automatisch.")}
              </p>
            </div>
            <footer className="modal-footer">
              <Button onClick={() => setPendingOffset(undefined)}>{t("Annuleren")}</Button>
              <Button
                onClick={() => {
                  const next = pendingOffset;
                  setPendingOffset(undefined);
                  void applyOffset(next);
                }}
              >
                {t("Handmatig instellen")}
              </Button>
            </footer>
          </section>
        </div>
      )}
      {headerUpdateOpen && headerUpdate && (
        <div
          className="modal-backdrop"
          role="presentation"
          onMouseDown={(event) => {
            if (
              event.target === event.currentTarget &&
              !headerUpdateApplying &&
              !headerUpdateReloading
            ) {
              setHeaderUpdateOpen(false);
            }
          }}
        >
          <section
            className="modal-card update-modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="update-dialog-title"
          >
            <div className="modal-header">
              <div>
                <h2 id="update-dialog-title">{t("Update installeren")}</h2>
                <p className="muted">
                  {headerUpdate.repository} · {headerUpdate.branch}
                </p>
              </div>
              <Button
                className="modal-close"
                aria-label={t("Sluiten")}
                disabled={headerUpdateApplying || headerUpdateReloading}
                onClick={() => setHeaderUpdateOpen(false)}
              >
                <X size={18} aria-hidden="true" />
              </Button>
            </div>
            <div className="stack">
              <p>
                {t(
                  "Er is een nieuwe release beschikbaar. Download de release van GitHub en vervang JS8Link wanneer de applicatie is afgesloten.",
                )}
              </p>
              <a
                className="button primary"
                href={headerUpdate.latest_url}
                target="_blank"
                rel="noreferrer"
              >
                {t("Open GitHub release")}
              </a>
              {headerUpdate.latest_message && (
                <div className="info-box">
                  <strong>{t("Nieuwste wijziging")}</strong>
                  <span>{headerUpdate.latest_message}</span>
                </div>
              )}
              {headerUpdate.reason && <div className="warning-text">{t(headerUpdate.reason)}</div>}
              {headerUpdateReloading && (
                <div className="info-box">
                  <strong>{t("Update geïnstalleerd")}</strong>
                  <span>
                    {t("De applicatie wordt herstart en deze pagina wordt opnieuw geladen…")}
                  </span>
                </div>
              )}
              {headerUpdateError && <div className="error">{headerUpdateError}</div>}
            </div>
            <div className="modal-actions">
              <Button
                disabled={headerUpdateApplying || headerUpdateReloading}
                onClick={() => setHeaderUpdateOpen(false)}
              >
                {t("Annuleren")}
              </Button>
              {headerUpdate.can_update && (
                <Button
                  className="primary"
                  disabled={headerUpdateApplying || headerUpdateReloading}
                  onClick={() => void applyHeaderUpdate()}
                >
                  {headerUpdateApplying ? t("Update installeren…") : t("Bevestigen en installeren")}
                </Button>
              )}
            </div>
          </section>
        </div>
      )}
      {changelogOpen && (
        <div
          className="modal-backdrop"
          role="presentation"
          onMouseDown={(event) => {
            if (event.target === event.currentTarget) setChangelogOpen(false);
          }}
        >
          <section
            className="modal-card changelog-modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="changelog-dialog-title"
          >
            <div className="modal-header">
              <div>
                <h2 id="changelog-dialog-title">{t("Changelog")}</h2>
                <p className="muted">JS8Link v{appVersion || "…"}</p>
              </div>
              <Button
                className="modal-close"
                aria-label={t("Sluiten")}
                onClick={() => setChangelogOpen(false)}
              >
                <X size={18} aria-hidden="true" />
              </Button>
            </div>
            {changelogLoading && <p className="muted">{t("Changelog laden…")}</p>}
            {changelogError && <div className="error">{changelogError}</div>}
            {!changelogLoading && !changelogError && (
              <div className="changelog-releases">
                {changelogReleases.map((release) => (
                  <section className="changelog-release" key={release.version}>
                    <div className="changelog-release-heading">
                      <h3>
                        {release.version === "Unreleased" ? t("Binnenkort") : `v${release.version}`}
                      </h3>
                      {release.date && <span className="muted">{release.date}</span>}
                    </div>
                    {release.categories.map((category) => (
                      <div className="changelog-category" key={category.name}>
                        <h4>{category.name}</h4>
                        <ul>
                          {category.items.map((item) => (
                            <li key={item}>{item}</li>
                          ))}
                        </ul>
                      </div>
                    ))}
                  </section>
                ))}
              </div>
            )}
          </section>
        </div>
      )}
    </div>
  );
}
