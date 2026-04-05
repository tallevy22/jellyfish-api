import { useState, useEffect, useCallback } from "react";

// ── הכנס את ה-URL של השרת שלך אחרי deploy ב-Render ──────────────────────────
const DEFAULT_API_URL = "https://jellyfish-api.onrender.com";
// לפיתוח מקומי: "http://localhost:8000"

const SEA_REGIONS = {
  "ים תיכון":           "mediterranean",
  "ים אדום":            "red_sea",
  "ים השחור":           "black_sea",
  "ים הצפון":           "north_sea",
  "האוקיינוס האטלנטי": "atlantic",
  "האוקיינוס השקט":    "pacific",
};

const TAXA = {
  "Scyphozoa (מדוזות אמיתיות)": "scyphozoa",
  "Medusozoa (כל המדוזות)":     "medusozoa",
  "Physalia (ספינת מלחמה)":     "physalia",
};

const MONTHS      = ["ינ׳","פב׳","מר׳","אפ׳","מאי","יונ׳","יול׳","אוג׳","ספט׳","אוק׳","נוב׳","דצ׳"];
const MONTHS_FULL = ["ינואר","פברואר","מרץ","אפריל","מאי","יוני","יולי","אוגוסט","ספטמבר","אוקטובר","נובמבר","דצמבר"];

const SOURCES = {
  inaturalist: { label: "iNaturalist",   icon: "🔬", color: "#34d399", weight: "30%" },
  youtube:     { label: "YouTube",       icon: "▶️",  color: "#f87171", weight: "18%" },
  mediacloud:  { label: "MediaCloud",    icon: "📰", color: "#f472b6", weight: "20%" },
  reddit:      { label: "Reddit",        icon: "💬", color: "#fb923c", weight: "17%" },
  trends:      { label: "Google Trends", icon: "📈", color: "#60a5fa", weight: "15%" },
};

function riskOf(score) {
  if (score < 8)  return { label: "נמוך מאוד", bg: "#064e3b", text: "#6ee7b7" };
  if (score < 25) return { label: "נמוך",      bg: "#065f46", text: "#34d399" };
  if (score < 50) return { label: "בינוני",    bg: "#78350f", text: "#fcd34d" };
  if (score < 75) return { label: "גבוה",      bg: "#7c2d12", text: "#fb923c" };
  return               { label: "גבוה מאוד", bg: "#7f1d1d", text: "#f87171" };
}

// ── Sub-components ─────────────────────────────────────────────────────────
function StatusDot({ status }) {
  const color = status === "live" ? "#4ade80" : status === "error" || status === "no_key" ? "#f87171" : "#fbbf24";
  const label = status === "live" ? "חי" : status === "no_key" ? "אין מפתח" : status === "error" ? "שגיאה" : status || "—";
  return (
    <span style={{ display:"inline-flex", alignItems:"center", gap:4, fontSize:9, color, background:"#0f172a", padding:"1px 7px", borderRadius:10, border:`1px solid ${color}44` }}>
      <span style={{ width:5, height:5, borderRadius:"50%", background:color, display:"inline-block" }} />
      {label}
    </span>
  );
}

function MiniBar({ data, color, currentMonth, height = 60 }) {
  const max = Math.max(...(data || []), 1);
  return (
    <div style={{ display:"flex", alignItems:"flex-end", gap:2, height }}>
      {(data || Array(12).fill(0)).map((v, i) => (
        <div key={i} style={{ flex:1, display:"flex", flexDirection:"column", alignItems:"center" }}>
          <div style={{
            width:"100%",
            height:`${Math.max(2, (v / max) * (height - 14))}px`,
            background: i === currentMonth ? color : color + "44",
            borderRadius:"2px 2px 0 0",
            boxShadow: i === currentMonth ? `0 0 8px ${color}88` : "none",
            transition:"height 0.5s ease",
          }} title={`${MONTHS_FULL[i]}: ${Math.round(v)}`} />
          <div style={{ fontSize:6.5, color: i === currentMonth ? color : "#374151", marginTop:2 }}>{MONTHS[i]}</div>
        </div>
      ))}
    </div>
  );
}

function ScoreGauge({ score }) {
  const risk = riskOf(score);
  const r = 36, circ = 2 * Math.PI * r;
  const dash = (Math.min(score, 100) / 100) * circ;
  return (
    <div style={{ display:"flex", flexDirection:"column", alignItems:"center", gap:6 }}>
      <svg width={96} height={96} style={{ transform:"rotate(-90deg)" }}>
        <circle cx={48} cy={48} r={r} fill="none" stroke="#1e293b" strokeWidth={8} />
        <circle cx={48} cy={48} r={r} fill="none" stroke={risk.text} strokeWidth={8}
          strokeDasharray={`${dash} ${circ}`} strokeLinecap="round"
          style={{ filter:`drop-shadow(0 0 6px ${risk.text}88)`, transition:"stroke-dasharray 0.8s ease" }} />
        <text x={48} y={54} textAnchor="middle" style={{ transform:"rotate(90deg)", transformOrigin:"48px 48px" }}
          fill={risk.text} fontSize={20} fontFamily="serif" fontWeight="bold">{Math.round(score)}</text>
      </svg>
      <div style={{ fontSize:13, color:risk.text, fontWeight:"bold" }}>{risk.label}</div>
    </div>
  );
}

// ── Main App ───────────────────────────────────────────────────────────────
export default function App() {
  const [apiUrl, setApiUrl]         = useState(DEFAULT_API_URL);
  const [apiUrlInput, setApiUrlInput] = useState(DEFAULT_API_URL);
  const [showUrlInput, setShowUrlInput] = useState(false);

  const [regionLabel, setRegionLabel] = useState("ים תיכון");
  const [taxonLabel,  setTaxonLabel]  = useState("Scyphozoa (מדוזות אמיתיות)");
  const [year, setYear]               = useState(new Date().getFullYear());
  const [tab,  setTab]                = useState("overview");

  const [loading,  setLoading]  = useState(false);
  const [progress, setProgress] = useState(0);
  const [apiReachable, setApiReachable] = useState(null); // null=unknown, true, false

  // data
  const [combined,   setCombined]   = useState({ monthly_scores: Array(12).fill(0), statuses: {}, sources: {}, peak_month: 0, current_score: 0 });
  const [inatRecent, setInatRecent] = useState([]);
  const [ytRecent,   setYtRecent]   = useState([]);
  const [rdPosts,    setRdPosts]    = useState([]);
  const [tbPosts,    setTbPosts]    = useState([]);

  const currentMonth = new Date().getMonth();
  const region = SEA_REGIONS[regionLabel];
  const taxon  = TAXA[taxonLabel];

  const apiFetch = useCallback(async (path) => {
    const r = await fetch(`${apiUrl}${path}`);
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    return r.json();
  }, [apiUrl]);

  const fetchAll = useCallback(async () => {
    setLoading(true); setProgress(5);

    // בדיקה שהשרת פעיל
    try {
      await fetch(`${apiUrl}/`);
      setApiReachable(true);
    } catch {
      setApiReachable(false);
      setLoading(false);
      return;
    }

    setProgress(15);

    try {
      // combined score (קורא את כל המקורות בצד שרת)
      const comb = await apiFetch(`/api/combined?region=${region}&taxon=${taxon}&year=${year}`);
      setCombined(comb);
      setProgress(50);

      // recent items במקביל
      const [inat, yt, rd, tb] = await Promise.allSettled([
        apiFetch(`/api/inaturalist?region=${region}&taxon=${taxon}&year=${year}`),
        apiFetch(`/api/youtube?region=${region}&year=${year}`),
        apiFetch(`/api/reddit?region=${region}&year=${year}`),
        apiFetch(`/api/tumblr?region=${region}`),
      ]);

      if (inat.status === "fulfilled") setInatRecent(inat.value.recent || []);
      if (yt.status   === "fulfilled") setYtRecent(yt.value.recent || []);
      if (rd.status   === "fulfilled") setRdPosts(rd.value.posts || []);
      if (tb.status   === "fulfilled") setTbPosts(tb.value.posts || []);

      setProgress(100);
    } catch (e) {
      console.error(e);
    }

    setLoading(false);
  }, [apiUrl, region, taxon, year, apiFetch]);

  useEffect(() => { fetchAll(); }, [fetchAll]);

  const scores   = combined.monthly_scores || Array(12).fill(0);
  const statuses = combined.statuses || {};
  const sources  = combined.sources  || {};
  const curScore = scores[currentMonth] || 0;
  const risk     = riskOf(curScore);
  const peakIdx  = scores.indexOf(Math.max(...scores));

  const tabs = ["overview", "iNaturalist", "YouTube", "Reddit", "מודל"];

  return (
    <div style={{ minHeight:"100vh", background:"#060a10", color:"#e2e8f0", fontFamily:"'Palatino Linotype',Palatino,serif", direction:"rtl" }}>

      {/* Progress bar */}
      {loading && (
        <div style={{ position:"fixed", top:0, left:0, right:0, height:2, zIndex:999, background:"#0f172a" }}>
          <div style={{ height:"100%", width:`${progress}%`, background:"linear-gradient(90deg,#34d399,#60a5fa,#f472b6)", transition:"width 0.4s" }} />
        </div>
      )}

      {/* HEADER */}
      <div style={{ padding:"20px 28px 14px", borderBottom:"1px solid #1e293b", background:"linear-gradient(180deg,#080c14 0%,transparent 100%)" }}>

        {/* API URL not reachable warning */}
        {apiReachable === false && (
          <div style={{ background:"#450a0a", border:"1px solid #dc2626", borderRadius:8, padding:"10px 16px", marginBottom:14, fontSize:12, color:"#fca5a5" }}>
            ⚠️ השרת לא נגיש: <code style={{ fontSize:11 }}>{apiUrl}</code>
            <div style={{ marginTop:4, color:"#f87171aa", fontSize:11 }}>
              ודא שה-Render service פועל, או הכנס URL נכון בהגדרות למטה.
            </div>
          </div>
        )}

        <div style={{ display:"flex", justifyContent:"space-between", alignItems:"flex-start", flexWrap:"wrap", gap:12 }}>
          <div>
            <div style={{ display:"flex", alignItems:"center", gap:10, marginBottom:6 }}>
              <span style={{ fontSize:26 }}>🪼</span>
              <h1 style={{ margin:0, fontSize:20, fontWeight:"normal", color:"#7dd3fc", letterSpacing:0.5 }}>מעקב התפרצויות מדוזות</h1>
            </div>
            {/* Source status badges */}
            <div style={{ display:"flex", gap:8, flexWrap:"wrap", marginRight:36 }}>
              {Object.entries(SOURCES).map(([k, v]) => (
                <div key={k} style={{ display:"flex", alignItems:"center", gap:5, padding:"3px 9px", background:"#0f172a", border:`1px solid ${v.color}33`, borderRadius:20, fontSize:11 }}>
                  <span>{v.icon}</span>
                  <span style={{ color:v.color }}>{v.label}</span>
                  <StatusDot status={statuses[k]} />
                </div>
              ))}
            </div>
          </div>

          {/* Risk badge */}
          <div style={{ background:risk.bg, border:`1px solid ${risk.text}44`, borderRadius:12, padding:"10px 18px", textAlign:"center", boxShadow:`0 0 20px ${risk.text}22` }}>
            <div style={{ fontSize:10, color:`${risk.text}99`, marginBottom:2 }}>סיכון נוכחי · {MONTHS_FULL[currentMonth]}</div>
            <div style={{ fontSize:18, color:risk.text, fontWeight:"bold" }}>{risk.label}</div>
            <div style={{ fontSize:10, color:`${risk.text}88` }}>ציון {Math.round(curScore)}/100</div>
          </div>
        </div>

        {/* Controls */}
        <div style={{ display:"flex", gap:12, marginTop:14, flexWrap:"wrap", alignItems:"flex-end" }}>
          {[
            { label:"אזור", val:regionLabel, set:setRegionLabel, opts:Object.keys(SEA_REGIONS) },
            { label:"סוג",  val:taxonLabel,  set:setTaxonLabel,  opts:Object.keys(TAXA) },
            { label:"שנה",  val:year, set:v=>setYear(Number(v)), opts:[2024,2023,2022,2021] },
          ].map(({ label, val, set, opts }) => (
            <div key={label}>
              <div style={{ fontSize:10, color:"#4b5563", marginBottom:3 }}>{label}</div>
              <select value={val} onChange={e => set(e.target.value)}
                style={{ background:"#0f172a", border:"1px solid #1e3a5f", color:"#93c5fd", borderRadius:7, padding:"6px 12px", fontSize:12, fontFamily:"inherit", outline:"none", cursor:"pointer" }}>
                {opts.map(o => <option key={o} value={o}>{o}</option>)}
              </select>
            </div>
          ))}

          {/* API URL setting */}
          <div>
            <div style={{ fontSize:10, color:"#4b5563", marginBottom:3 }}>🔗 כתובת שרת</div>
            {showUrlInput ? (
              <div style={{ display:"flex", gap:4 }}>
                <input value={apiUrlInput} onChange={e => setApiUrlInput(e.target.value)}
                  placeholder="https://jellyfish-api.onrender.com"
                  style={{ background:"#0f172a", border:"1px solid #7dd3fc", color:"#bae6fd", borderRadius:7, padding:"6px 10px", fontSize:11, fontFamily:"monospace", width:220, outline:"none" }} />
                <button onClick={() => { setApiUrl(apiUrlInput); setShowUrlInput(false); }}
                  style={{ background:"#0c4a6e", border:"1px solid #7dd3fc", color:"#bae6fd", borderRadius:7, padding:"6px 10px", fontSize:11, cursor:"pointer" }}>✓</button>
                <button onClick={() => setShowUrlInput(false)}
                  style={{ background:"#0f172a", border:"1px solid #374151", color:"#6b7280", borderRadius:7, padding:"6px 8px", fontSize:11, cursor:"pointer" }}>✕</button>
              </div>
            ) : (
              <button onClick={() => setShowUrlInput(true)}
                style={{ background:"#0f172a", border:`1px solid ${apiReachable === true ? "#4ade80" : apiReachable === false ? "#f87171" : "#374151"}`, color: apiReachable === true ? "#4ade80" : apiReachable === false ? "#f87171" : "#4b5563", borderRadius:7, padding:"6px 12px", fontSize:11, cursor:"pointer", fontFamily:"monospace" }}>
                {apiUrl.replace("https://","").slice(0,30)}{apiUrl.length > 35 ? "…" : ""}
              </button>
            )}
          </div>

          <button onClick={fetchAll} disabled={loading}
            style={{ padding:"7px 18px", background: loading ? "#0f172a" : "#1e3a5f", border:"1px solid #3b82f6", borderRadius:7, color:"#93c5fd", cursor: loading ? "not-allowed" : "pointer", fontSize:12, fontFamily:"inherit" }}>
            {loading ? `טוען… ${progress}%` : "🔄 עדכן"}
          </button>
        </div>
      </div>

      {/* TABS */}
      <div style={{ display:"flex", borderBottom:"1px solid #1e293b", padding:"0 28px", overflowX:"auto" }}>
        {tabs.map(t => (
          <button key={t} onClick={() => setTab(t)}
            style={{ padding:"10px 16px", background:"transparent", border:"none", borderBottom: tab===t ? "2px solid #7dd3fc" : "2px solid transparent", color: tab===t ? "#7dd3fc" : "#4b5563", cursor:"pointer", fontSize:12, fontFamily:"inherit", whiteSpace:"nowrap" }}>
            {t}
          </button>
        ))}
      </div>

      {/* CONTENT */}
      <div style={{ padding:"24px 28px" }}>

        {/* ── OVERVIEW ── */}
        {tab === "overview" && (
          <div style={{ display:"flex", gap:20, flexWrap:"wrap" }}>

            {/* Gauge panel */}
            <div style={{ background:"#0a1628", border:"1px solid #1e293b", borderRadius:14, padding:"20px 24px", display:"flex", flexDirection:"column", alignItems:"center", gap:16, minWidth:180 }}>
              <ScoreGauge score={curScore} />
              <div style={{ textAlign:"center", width:"100%" }}>
                <div style={{ fontSize:11, color:"#4b5563" }}>חודש שיא</div>
                <div style={{ fontSize:16, color:"#fcd34d", marginBottom:10 }}>{peakIdx >= 0 ? MONTHS_FULL[peakIdx] : "—"}</div>
                {Object.entries(SOURCES).map(([k, v]) => (
                  <div key={k} style={{ display:"flex", justifyContent:"space-between", alignItems:"center", marginBottom:5 }}>
                    <span style={{ fontSize:10, color:v.color }}>{v.icon} {v.label}</span>
                    <span style={{ fontSize:10, color:"#374151" }}>{(sources[k] || []).reduce((a,b)=>a+b,0)}</span>
                  </div>
                ))}
              </div>
            </div>

            {/* Source bars */}
            <div style={{ flex:"1 1 420px", display:"flex", flexDirection:"column", gap:12 }}>
              {Object.entries(SOURCES).map(([k, v]) => (
                <div key={k} style={{ background:"#0a1628", border:"1px solid #1e293b", borderRadius:10, padding:"12px 16px" }}>
                  <div style={{ display:"flex", justifyContent:"space-between", marginBottom:6 }}>
                    <span style={{ fontSize:11, color:v.color }}>{v.icon} {v.label}</span>
                    <StatusDot status={statuses[k]} />
                  </div>
                  <MiniBar data={sources[k] || Array(12).fill(0)} color={v.color} currentMonth={currentMonth} />
                </div>
              ))}
            </div>
          </div>
        )}

        {/* ── iNaturalist ── */}
        {tab === "iNaturalist" && (
          <div style={{ display:"flex", gap:16, flexWrap:"wrap" }}>
            <div style={{ flex:"1 1 320px", background:"#0a1628", border:"1px solid #1e293b", borderRadius:14, padding:"18px 20px" }}>
              <h3 style={{ margin:"0 0 14px", fontSize:14, color:"#34d399", fontWeight:"normal" }}>🔬 תצפיות לפי חודש</h3>
              <MiniBar data={sources.inaturalist} color="#34d399" currentMonth={currentMonth} height={100} />
              <div style={{ marginTop:10, fontSize:12, color:"#4b5563" }}>
                סה״כ: <span style={{ color:"#34d399" }}>{(sources.inaturalist||[]).reduce((a,b)=>a+b,0).toLocaleString()}</span>
              </div>
            </div>
            <div style={{ flex:"1 1 280px", background:"#0a1628", border:"1px solid #1e293b", borderRadius:14, padding:"18px 20px" }}>
              <h3 style={{ margin:"0 0 12px", fontSize:14, color:"#34d399", fontWeight:"normal" }}>תצפיות אחרונות</h3>
              <div style={{ display:"flex", flexDirection:"column", gap:8 }}>
                {inatRecent.length === 0 && <div style={{ color:"#374151", fontSize:12 }}>אין תצפיות</div>}
                {inatRecent.map(o => (
                  <a key={o.id} href={o.url} target="_blank" rel="noreferrer"
                    style={{ display:"flex", gap:8, padding:"8px 10px", background:"#0f172a", border:"1px solid #1e293b", borderRadius:8, textDecoration:"none", color:"inherit" }}>
                    {o.photo
                      ? <img src={o.photo} alt="" style={{ width:44, height:44, objectFit:"cover", borderRadius:6, flexShrink:0 }} />
                      : <div style={{ width:44, height:44, background:"#1e293b", borderRadius:6, display:"flex", alignItems:"center", justifyContent:"center", fontSize:20, flexShrink:0 }}>🪼</div>
                    }
                    <div>
                      <div style={{ fontSize:11, color:"#34d399" }}>{o.taxon || "מדוזה"}</div>
                      <div style={{ fontSize:10, color:"#4b5563" }}>📍 {o.place || "מיקום לא ידוע"}</div>
                      <div style={{ fontSize:9, color:"#374151" }}>{o.date}</div>
                    </div>
                  </a>
                ))}
              </div>
            </div>
          </div>
        )}

        {/* ── YouTube ── */}
        {tab === "YouTube" && (
          <div style={{ display:"flex", gap:16, flexWrap:"wrap" }}>
            <div style={{ flex:"1 1 320px", background:"#0a1628", border:"1px solid #1e293b", borderRadius:14, padding:"18px 20px" }}>
              <h3 style={{ margin:"0 0 6px", fontSize:14, color:"#f87171", fontWeight:"normal" }}>▶️ YouTube לפי חודש</h3>
              <div style={{ fontSize:11, color:"#4b5563", marginBottom:12 }}><StatusDot status={statuses.youtube} /></div>
              <MiniBar data={sources.youtube} color="#f87171" currentMonth={currentMonth} height={100} />
            </div>
            {ytRecent.length > 0 && (
              <div style={{ flex:"1 1 280px", background:"#0a1628", border:"1px solid #1e293b", borderRadius:14, padding:"18px 20px" }}>
                <h3 style={{ margin:"0 0 12px", fontSize:14, color:"#f87171", fontWeight:"normal" }}>סרטונים אחרונים</h3>
                <div style={{ display:"flex", flexDirection:"column", gap:8 }}>
                  {ytRecent.map((v,i) => (
                    <a key={i} href={v.url} target="_blank" rel="noreferrer"
                      style={{ display:"flex", gap:8, padding:"8px 10px", background:"#0f172a", border:"1px solid #1e293b", borderRadius:8, textDecoration:"none" }}>
                      {v.thumbnail && <img src={v.thumbnail} alt="" style={{ width:48, height:36, objectFit:"cover", borderRadius:4, flexShrink:0 }} />}
                      <div>
                        <div style={{ fontSize:11, color:"#f87171", overflow:"hidden", textOverflow:"ellipsis", whiteSpace:"nowrap", maxWidth:200 }}>{v.title}</div>
                        <div style={{ fontSize:9, color:"#4b5563" }}>{v.channel} · {v.date}</div>
                      </div>
                    </a>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}

        {/* ── Reddit ── */}
        {tab === "Reddit" && (
          <div style={{ display:"flex", gap:16, flexWrap:"wrap" }}>
            <div style={{ flex:"1 1 340px", background:"#0a1628", border:"1px solid #1e293b", borderRadius:14, padding:"18px 20px" }}>
              <h3 style={{ margin:"0 0 6px", fontSize:14, color:"#fb923c", fontWeight:"normal" }}>💬 Reddit</h3>
              <div style={{ fontSize:11, color:"#4b5563", marginBottom:14 }}><StatusDot status={statuses.reddit} /></div>
              <div style={{ display:"flex", flexDirection:"column", gap:8 }}>
                {rdPosts.length === 0 && <div style={{ color:"#374151", fontSize:12 }}>אין פוסטים</div>}
                {rdPosts.map((p,i) => (
                  <a key={i} href={p.url} target="_blank" rel="noreferrer"
                    style={{ display:"block", padding:"8px 10px", background:"#0f172a", border:"1px solid #1e293b", borderRadius:8, textDecoration:"none" }}>
                    <div style={{ fontSize:11, color:"#fb923c", marginBottom:2, display:"-webkit-box", WebkitLineClamp:2, WebkitBoxOrient:"vertical", overflow:"hidden" }}>{p.title}</div>
                    <div style={{ fontSize:9, color:"#4b5563" }}>r/{p.subreddit} · {p.score} ↑ · {p.date}</div>
                  </a>
                ))}
              </div>
            </div>
          </div>
        )}

        {/* ── MODEL ── */}
        {tab === "מודל" && (
          <div style={{ display:"flex", gap:16, flexWrap:"wrap" }}>
            <div style={{ flex:"1 1 420px", background:"#0a1628", border:"1px solid #1e293b", borderRadius:14, padding:"18px 22px" }}>
              <h3 style={{ margin:"0 0 4px", fontSize:14, color:"#7dd3fc", fontWeight:"normal" }}>📊 ציון משולב לפי חודש</h3>
              <div style={{ fontSize:10, color:"#374151", marginBottom:16 }}>weighted average מכל המקורות</div>

              <div style={{ display:"flex", alignItems:"flex-end", gap:4, height:120 }}>
                {scores.map((v, i) => {
                  const r = riskOf(v);
                  return (
                    <div key={i} style={{ flex:1, display:"flex", flexDirection:"column", alignItems:"center" }}>
                      <div style={{ fontSize:8, color:r.text, marginBottom:2 }}>{Math.round(v)||""}</div>
                      <div style={{
                        width:"100%",
                        height:`${Math.max(4, (v/100)*100)}px`,
                        background:`linear-gradient(to top, ${r.bg}, ${r.text}66)`,
                        borderRadius:"3px 3px 0 0",
                        border: i===currentMonth ? `1px solid ${r.text}` : "none",
                        boxShadow: i===currentMonth ? `0 0 10px ${r.text}66` : "none",
                        transition:"height 0.6s",
                      }} title={`${MONTHS_FULL[i]}: ${Math.round(v)}/100`} />
                      <div style={{ fontSize:7.5, color: i===currentMonth ? "#7dd3fc" : "#374151", marginTop:2 }}>{MONTHS[i]}</div>
                    </div>
                  );
                })}
              </div>

              {/* Weights */}
              <div style={{ marginTop:20 }}>
                <div style={{ fontSize:11, color:"#4b5563", marginBottom:8 }}>משקל לפי מקור</div>
                {Object.entries(SOURCES).map(([k, v]) => (
                  <div key={k} style={{ display:"flex", alignItems:"center", gap:8, marginBottom:6 }}>
                    <div style={{ width:`${parseFloat(v.weight)*2}px`, height:6, background:v.color, borderRadius:3 }} />
                    <span style={{ fontSize:11, color:v.color }}>{v.icon} {v.label}</span>
                    <span style={{ fontSize:10, color:"#374151", marginRight:"auto" }}>{v.weight}</span>
                    <StatusDot status={statuses[k]} />
                  </div>
                ))}
              </div>

              {/* Setup guide */}
              <div style={{ marginTop:16, padding:"12px 14px", background:"#060a10", border:"1px solid #1e293b", borderRadius:8, fontSize:11, color:"#4b5563", lineHeight:1.8 }}>
                <div style={{ color:"#7dd3fc", marginBottom:6, fontSize:12 }}>🚀 הגדרת השרת</div>
                <div>1. צור repo ב-GitHub עם קבצי ה-backend</div>
                <div>2. חבר ל-<a href="https://render.com" target="_blank" rel="noreferrer" style={{ color:"#93c5fd" }}>render.com</a> → New Web Service</div>
                <div>3. הוסף env vars: <code style={{ color:"#f87171", fontSize:10 }}>YOUTUBE_API_KEY</code>, <code style={{ color:"#f472b6", fontSize:10 }}>MEDIACLOUD_API_KEY</code></div>
                <div>4. הכנס את ה-URL שקיבלת בשדה "כתובת שרת" למעלה</div>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
