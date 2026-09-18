"use client";

import { useState, useEffect, useRef } from "react";
import axios from "axios";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1";

type Phase = "boot" | "auth" | "app";

type ChatMsg = {
  role: "user" | "assistant";
  content: string;
  model_used?: string;
  query_type?: string;
  token_cost?: number;
  latency_ms?: number;
};

const PROCESS_STAGES = [
  "Sinyal alındı",
  "Niyet çözülüyor",
  "Motor seçiliyor",
  "Muhakeme çalışıyor",
  "Yanıt hizalanıyor",
];

export default function Home() {
  const [phase, setPhase] = useState<Phase>("boot");
  const [bootStep, setBootStep] = useState(0);
  const [token, setToken] = useState<string | null>(null);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [fullName, setFullName] = useState("");
  const [isLogin, setIsLogin] = useState(true);
  const [message, setMessage] = useState("");
  const [messages, setMessages] = useState<ChatMsg[]>([]);
  const [tokensLeft, setTokensLeft] = useState<number | null>(null);
  const [loading, setLoading] = useState(false);
  const [stageIdx, setStageIdx] = useState(0);
  const [elapsed, setElapsed] = useState(0);
  const [error, setError] = useState("");
  const [symbol, setSymbol] = useState("");
  const [showMarket, setShowMarket] = useState(false);
  const [showAttach, setShowAttach] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const loadStarted = useRef(0);
  const [acceptTypes, setAcceptTypes] = useState("*/*");

  useEffect(() => {
    const timers = [
      setTimeout(() => setBootStep(1), 600),
      setTimeout(() => setBootStep(2), 2000),
      setTimeout(() => setBootStep(3), 4000),
      setTimeout(() => setBootStep(4), 6200),
      setTimeout(() => setBootStep(5), 8500),
      setTimeout(() => {
        const saved = localStorage.getItem("nexora_token");
        if (saved) {
          setToken(saved);
          setPhase("app");
          fetchMe(saved);
        } else setPhase("auth");
      }, 11000),
    ];
    return () => timers.forEach(clearTimeout);
  }, []);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading, stageIdx, elapsed]);

  useEffect(() => {
    if (!loading) return;
    const stageTimer = setInterval(() => setStageIdx((i) => (i + 1) % PROCESS_STAGES.length), 1400);
    const clock = setInterval(() => setElapsed((Date.now() - loadStarted.current) / 1000), 100);
    return () => {
      clearInterval(stageTimer);
      clearInterval(clock);
    };
  }, [loading]);

  const fetchMe = async (accessToken: string) => {
    try {
      const res = await axios.get(`${API_URL}/auth/me`, {
        headers: { Authorization: `Bearer ${accessToken}` },
      });
      if (typeof res.data.tokens === "number") setTokensLeft(res.data.tokens);
    } catch { /* ignore */ }
  };

  const startLoad = () => {
    setLoading(true);
    setStageIdx(0);
    loadStarted.current = Date.now();
    setElapsed(0);
    setError("");
  };

  const handleAuth = async () => {
    setError("");
    try {
      if (isLogin) {
        const res = await axios.post(`${API_URL}/auth/login`, { email, password });
        const access = res.data.access_token;
        localStorage.setItem("nexora_token", access);
        setToken(access);
        setPhase("app");
        await fetchMe(access);
      } else {
        await axios.post(`${API_URL}/auth/register`, { email, password, full_name: fullName });
        setIsLogin(true);
        setError("Kayıt tamam. 50 token yüklendi — giriş yap.");
      }
    } catch (err: any) {
      setError(err.response?.data?.detail || "Bir hata oluştu");
    }
  };

  const sendMessage = async () => {
    if (!message.trim() || !token || loading) return;
    setShowAttach(false);
    startLoad();
    const newMessages: ChatMsg[] = [...messages, { role: "user", content: message }];
    setMessages(newMessages);
    setMessage("");
    try {
      const res = await axios.post(
        `${API_URL}/chat`,
        { messages: newMessages.map((m) => ({ role: m.role, content: m.content })), stream: false },
        { headers: { Authorization: `Bearer ${token}` } }
      );
      const clientMs = Date.now() - loadStarted.current;
      setMessages([
        ...newMessages,
        {
          role: "assistant",
          content: res.data.content,
          model_used: res.data.model_used,
          query_type: res.data.query_type,
          token_cost: res.data.token_cost,
          latency_ms: res.data.latency_ms || clientMs,
        },
      ]);
      if (typeof res.data.tokens === "number") setTokensLeft(res.data.tokens);
    } catch (err: any) {
      setError(err.response?.data?.detail || "Mesaj gönderilemedi");
    } finally {
      setLoading(false);
    }
  };

  const analyzeMarket = async () => {
    if (!symbol.trim() || !token || loading) return;
    startLoad();
    setShowMarket(false);
    try {
      const res = await axios.post(
        `${API_URL}/market/analyze`,
        { symbol: symbol.trim() },
        { headers: { Authorization: `Bearer ${token}` } }
      );
      const clientMs = Date.now() - loadStarted.current;
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: `ANALİZ — ${res.data.symbol}\n\n${res.data.analysis}`,
          query_type: "finance",
          model_used: res.data.model_used || "nexora-market",
          token_cost: res.data.token_cost ?? 3,
          latency_ms: res.data.latency_ms || clientMs,
        },
      ]);
      if (typeof res.data.tokens === "number") setTokensLeft(res.data.tokens);
    } catch (err: any) {
      setError(err.response?.data?.detail || "Analiz yapılamadı");
    } finally {
      setLoading(false);
      setSymbol("");
    }
  };

  const openFilePicker = (kind: "image" | "file" | "audio") => {
    setShowAttach(false);
    if (kind === "image") setAcceptTypes("image/jpeg,image/png,image/webp,image/gif");
    else if (kind === "audio") setAcceptTypes("audio/mpeg,audio/wav,audio/webm,audio/*");
    else setAcceptTypes(".txt,.md,.csv,.json,.pdf,text/plain,application/pdf");
    setTimeout(() => fileRef.current?.click(), 50);
  };

  const onFileSelected = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file || !token || loading) return;

    setMessages((prev) => [...prev, { role: "user", content: `📎 ${file.name}` }]);
    startLoad();

    const form = new FormData();
    form.append("file", file);
    form.append("prompt", message.trim() || "Bu içeriği analiz et.");

    try {
      const res = await axios.post(`${API_URL}/media/analyze`, form, {
        headers: { Authorization: `Bearer ${token}` },
      });
      const clientMs = Date.now() - loadStarted.current;
      const note = res.data.note ? `\n\n_${res.data.note}_` : "";
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: res.data.analysis + note,
          model_used: res.data.model_used,
          query_type: res.data.kind,
          token_cost: res.data.token_cost,
          latency_ms: clientMs,
        },
      ]);
      if (typeof res.data.tokens === "number") setTokensLeft(res.data.tokens);
      setMessage("");
    } catch (err: any) {
      setError(err.response?.data?.detail || "Yükleme başarısız");
    } finally {
      setLoading(false);
    }
  };

  const upgrade = async (plan: "pro" | "elite") => {
    if (!token) return;
    try {
      const res = await axios.post(
        `${API_URL}/payments/create-checkout`,
        { plan },
        { headers: { Authorization: `Bearer ${token}` } }
      );
      if (res.data.checkout_url) window.location.href = res.data.checkout_url;
    } catch (err: any) {
      setError(err.response?.data?.detail || "Ödeme başlatılamadı");
    }
  };

  const logout = () => {
    localStorage.removeItem("nexora_token");
    setToken(null);
    setMessages([]);
    setTokensLeft(null);
    setPhase("auth");
  };

  const shortModel = (m?: string) => {
    if (!m) return "";
    const p = m.split("/").pop() || m;
    return p.length > 28 ? p.slice(0, 26) + "…" : p;
  };

  const typeLabel = (t?: string) => {
    const map: Record<string, string> = {
      finance: "finans",
      code: "kod",
      deep: "derin",
      fast: "hızlı",
      identity: "kimlik",
      image: "görsel",
      file: "dosya",
      audio: "ses",
    };
    return t ? map[t] || t : "";
  };

  const fmtSec = (ms?: number) => (ms == null ? "" : `${(ms / 1000).toFixed(1)} sn`);

  /* BOOT — aynı */
  if (phase === "boot") {
    return (
      <div style={s.bootScreen}>
        {bootStep >= 1 && (
          <div style={s.bootCenter}>
            <div style={s.bootBrand}>NEXORA</div>
            {bootStep === 1 && <div style={s.bootMuted}>Initializing...</div>}
          </div>
        )}
        {bootStep >= 2 && bootStep < 4 && (
          <div style={s.bootCenter}>
            <div style={s.bootBrand}>NEXORA CORE</div>
            <div style={s.bootLines}>
              <div>Initializing Nexora Core...</div>
              <div>Loading intelligence modules...</div>
              {bootStep >= 3 && <div>Connecting reasoning engine...</div>}
              {bootStep >= 3 && <div>Building knowledge map...</div>}
            </div>
          </div>
        )}
        {bootStep >= 4 && bootStep < 5 && (
          <div style={s.bootCenter}>
            <div style={s.bootBrand}>SYSTEM BOOT</div>
            <div style={s.bootChecks}>
              <div>✓ Neural Engine Connected</div>
              <div>✓ Reasoning Layer Active</div>
              <div>✓ Knowledge Network Online</div>
              <div>✓ Intelligence Core Ready</div>
            </div>
          </div>
        )}
        {bootStep >= 5 && (
          <div style={s.bootCenter}>
            <div style={s.bootBrand}>NEXORA AI</div>
            <div style={s.bootTagline}>Not a chatbot. An intelligence system.</div>
            <div style={s.bootMuted}>SYSTEM READY</div>
          </div>
        )}
      </div>
    );
  }

  /* AUTH — aynı */
  if (phase === "auth") {
    return (
      <div style={s.page}>
        <div style={s.authWrap}>
          <div style={s.authHeader}>
            <div style={s.brandBig}>NEXORA</div>
            <div style={s.brandSub}>AI CORE</div>
            <div style={s.tagline}>Not a chatbot. An intelligence system.</div>
          </div>
          <div style={s.statusBox}>
            <div style={s.statusTitle}>SYSTEM STATUS</div>
            <div style={s.statusLine}><span style={s.dot}>●</span> Neural Engine ONLINE</div>
            <div style={s.statusLine}><span style={s.dot}>●</span> Reasoning Layer ACTIVE</div>
            <div style={s.statusLine}><span style={s.dot}>●</span> Knowledge Network CONNECTED</div>
            <div style={s.statusLine}><span style={s.dot}>●</span> Processing Core RUNNING</div>
          </div>
          <div style={s.authCard}>
            <div style={s.authLabel}>{isLogin ? "ACCESS CORE" : "CREATE ACCESS"}</div>
            {!isLogin && (
              <input placeholder="Ad soyad" value={fullName} onChange={(e) => setFullName(e.target.value)} style={s.input} />
            )}
            <input placeholder="Email" value={email} onChange={(e) => setEmail(e.target.value)} style={s.input} />
            <input type="password" placeholder="Şifre" value={password} onChange={(e) => setPassword(e.target.value)} style={s.input} onKeyDown={(e) => e.key === "Enter" && handleAuth()} />
            {error && <div style={s.error}>{error}</div>}
            <button onClick={handleAuth} style={s.primaryBtn}>
              {isLogin ? "Initialize Core" : "Register · 50 Token"}
            </button>
            <div style={s.switch} onClick={() => { setIsLogin(!isLogin); setError(""); }}>
              {isLogin ? "Hesabın yok mu? Kayıt ol" : "Hesabın var mı? Giriş yap"}
            </div>
          </div>
        </div>
      </div>
    );
  }

  /* APP */
  return (
    <div style={s.page}>
      <input ref={fileRef} type="file" accept={acceptTypes} style={{ display: "none" }} onChange={onFileSelected} />

      <header style={s.header}>
        <div style={s.headerLeft}>
          <div style={s.brandSmall}>NEXORA</div>
          <div style={s.coreBadge}>CORE · ONLINE</div>
          {tokensLeft !== null && <div style={s.tokenBadge}>{tokensLeft} token</div>}
        </div>
        <div style={s.headerRight}>
          <button onClick={() => setShowMarket(!showMarket)} style={s.ghostBtn}>Analyze</button>
          <button onClick={() => upgrade("pro")} style={s.ghostBtn}>Pro</button>
          <button onClick={() => upgrade("elite")} style={s.ghostBtn}>Elite</button>
          <button onClick={logout} style={s.ghostBtn}>Exit</button>
        </div>
      </header>

      {showMarket && (
        <div style={s.marketBar}>
          <input value={symbol} onChange={(e) => setSymbol(e.target.value)} placeholder="Sembol (BTC, ASELSAN…)" style={{ ...s.input, marginBottom: 0, flex: 1 }} onKeyDown={(e) => e.key === "Enter" && analyzeMarket()} />
          <button onClick={analyzeMarket} disabled={loading} style={s.primaryBtnSmall}>Run</button>
        </div>
      )}

      <main style={s.chatArea}>
        {messages.length === 0 && !loading && (
          <div style={s.empty}>
            <div style={s.emptyTitle}>NEXORA CORE</div>
            <div style={s.emptySub}>STATUS: ONLINE</div>
            <div style={s.emptyHint}>Ask. Analyze. Create.</div>
          </div>
        )}

        {messages.map((m, i) => (
          <div key={i} style={{ ...s.bubble, alignSelf: m.role === "user" ? "flex-end" : "flex-start", borderColor: m.role === "user" ? "#1a1a1a" : "rgba(0,240,255,0.25)" }}>
            <div style={s.bubbleLabel}>{m.role === "user" ? "USER" : "NEXORA"}</div>
            <div style={s.bubbleText}>{m.content}</div>
            {m.role === "assistant" && (
              <div style={s.meta}>
                {m.query_type && <span>mod: {typeLabel(m.query_type)}</span>}
                {m.model_used && <span> · motor: {shortModel(m.model_used)}</span>}
                {m.token_cost != null && <span> · −{m.token_cost} token</span>}
                {m.latency_ms != null && <span> · {fmtSec(m.latency_ms)}</span>}
              </div>
            )}
          </div>
        ))}

        {loading && (
          <div style={{ ...s.bubble, ...s.processCard, alignSelf: "flex-start" }}>
            <div style={s.bubbleLabel}>NEXORA PROCESS</div>
            <div style={s.stageRow}>
              <span style={s.pulse} />
              <div>
                <div style={s.stageTitle}>{PROCESS_STAGES[stageIdx]}</div>
                <div style={s.stageClock}>{elapsed.toFixed(1)}s</div>
              </div>
            </div>
            <div style={s.stageBar}>
              <div style={{ ...s.stageFill, width: `${((stageIdx + 1) / PROCESS_STAGES.length) * 100}%` }} />
            </div>
            <div style={s.meta}>Sistem çalışıyor · donmadı</div>
          </div>
        )}
        <div ref={bottomRef} />
      </main>

      {error && <div style={{ ...s.error, padding: "0 20px 8px" }}>{error}</div>}

      {showAttach && (
        <div style={s.attachMenu}>
          <button type="button" style={s.attachItem} onClick={() => openFilePicker("image")}>Foto · +2</button>
          <button type="button" style={s.attachItem} onClick={() => openFilePicker("file")}>Belge · +2</button>
          <button type="button" style={s.attachItem} onClick={() => openFilePicker("audio")}>Ses · +3</button>
          <button type="button" style={s.attachItem} onClick={() => { setShowAttach(false); setError("Video yakında · +4 token"); }}>Video · +4</button>
        </div>
      )}

      <div style={s.inputBar}>
        <button type="button" style={s.plusBtn} onClick={() => setShowAttach(!showAttach)} disabled={loading}>+</button>
        <input value={message} onChange={(e) => setMessage(e.target.value)} onKeyDown={(e) => e.key === "Enter" && !e.shiftKey && sendMessage()} placeholder="Transmit to core…" disabled={loading} style={{ ...s.input, marginBottom: 0, flex: 1, opacity: loading ? 0.6 : 1 }} />
        <button onClick={sendMessage} disabled={loading} style={s.primaryBtnSmall}>{loading ? "…" : "Send"}</button>
      </div>
    </div>
  );
}

const s: { [key: string]: React.CSSProperties } = {
  bootScreen: { minHeight: "100vh", background: "#000", color: "#e8e8e8", display: "flex", alignItems: "center", justifyContent: "center", fontFamily: "ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace" },
  bootCenter: { textAlign: "center", maxWidth: 480, padding: 24 },
  bootBrand: { fontSize: 28, fontWeight: 600, letterSpacing: 8, marginBottom: 24 },
  bootMuted: { color: "#555", fontSize: 13, letterSpacing: 2, marginTop: 16 },
  bootTagline: { color: "#aaa", fontSize: 14, marginTop: 12, letterSpacing: 1 },
  bootLines: { color: "#666", fontSize: 13, lineHeight: 2, textAlign: "left" },
  bootChecks: { color: "#00F0FF", fontSize: 13, lineHeight: 2, textAlign: "left" },
  page: { minHeight: "100vh", background: "#0D0D1A", color: "#e0e0e0", fontFamily: "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif", display: "flex", flexDirection: "column" },
  authWrap: { margin: "auto", width: "100%", maxWidth: 440, padding: 24 },
  authHeader: { textAlign: "center", marginBottom: 28 },
  brandBig: { fontSize: 32, fontWeight: 700, letterSpacing: 6 },
  brandSub: { fontSize: 12, color: "#00F0FF", letterSpacing: 4, marginTop: 4 },
  tagline: { fontSize: 13, color: "#777", marginTop: 12 },
  statusBox: { border: "1px solid #1a1a2e", padding: 16, marginBottom: 20, fontFamily: "ui-monospace, monospace", fontSize: 12 },
  statusTitle: { color: "#555", marginBottom: 10, letterSpacing: 2 },
  statusLine: { marginBottom: 4, color: "#aaa" },
  dot: { color: "#00F0FF", marginRight: 8 },
  authCard: { border: "1px solid #1a1a2e", padding: 20 },
  authLabel: { fontSize: 11, letterSpacing: 2, color: "#666", marginBottom: 14 },
  input: { width: "100%", padding: "12px 14px", marginBottom: 10, borderRadius: 0, border: "1px solid #222", background: "#0a0a12", color: "#eee", fontSize: 14, outline: "none" },
  primaryBtn: { width: "100%", padding: "12px", border: "1px solid #00F0FF", background: "transparent", color: "#00F0FF", fontWeight: 600, fontSize: 13, letterSpacing: 1, cursor: "pointer", marginTop: 6 },
  primaryBtnSmall: { padding: "12px 18px", border: "1px solid #00F0FF", background: "transparent", color: "#00F0FF", fontWeight: 600, fontSize: 13, cursor: "pointer", whiteSpace: "nowrap" },
  switch: { textAlign: "center", marginTop: 14, color: "#666", fontSize: 12, cursor: "pointer" },
  error: { color: "#ff4466", fontSize: 12, marginBottom: 8 },
  header: { display: "flex", justifyContent: "space-between", alignItems: "center", padding: "12px 20px", borderBottom: "1px solid #151520", flexWrap: "wrap", gap: 10 },
  headerLeft: { display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap" },
  brandSmall: { fontWeight: 700, letterSpacing: 3, fontSize: 14 },
  coreBadge: { fontSize: 10, color: "#00F0FF", letterSpacing: 1 },
  tokenBadge: { fontSize: 11, color: "#0D0D1A", background: "linear-gradient(90deg, #00F0FF, #7B2CFF)", padding: "3px 10px", fontWeight: 700 },
  headerRight: { display: "flex", gap: 8, flexWrap: "wrap" },
  ghostBtn: { padding: "7px 12px", border: "1px solid #222", background: "transparent", color: "#999", fontSize: 12, cursor: "pointer" },
  marketBar: { display: "flex", gap: 10, padding: "10px 20px", borderBottom: "1px solid #151520" },
  chatArea: { flex: 1, overflowY: "auto", padding: 20, display: "flex", flexDirection: "column", gap: 12 },
  empty: { margin: "auto", textAlign: "center", maxWidth: 560 },
  emptyTitle: { fontSize: 22, letterSpacing: 4, fontWeight: 600 },
  emptySub: { color: "#00F0FF", fontSize: 11, letterSpacing: 2, marginTop: 8 },
  emptyHint: { color: "#555", marginTop: 16, fontSize: 14 },
  bubble: { maxWidth: "85%", padding: "12px 14px", border: "1px solid #1a1a1a", background: "#0a0a12" },
  processCard: { borderColor: "rgba(0,240,255,0.4)" },
  bubbleLabel: { fontSize: 10, color: "#00F0FF", letterSpacing: 1, marginBottom: 6 },
  bubbleText: { whiteSpace: "pre-wrap", lineHeight: 1.5, fontSize: 14 },
  meta: { marginTop: 10, fontSize: 10, color: "#666" },
  stageRow: { display: "flex", gap: 12, alignItems: "center" },
  pulse: { width: 8, height: 8, borderRadius: "50%", background: "#00F0FF", boxShadow: "0 0 12px #00F0FF", flexShrink: 0 },
  stageTitle: { fontSize: 14, color: "#ddd" },
  stageClock: { fontSize: 12, color: "#00F0FF", marginTop: 2, fontVariantNumeric: "tabular-nums" },
  stageBar: { marginTop: 12, height: 2, background: "rgba(255,255,255,0.06)", overflow: "hidden" },
  stageFill: { height: "100%", background: "linear-gradient(90deg, #00F0FF, #7B2CFF)", transition: "width 0.35s ease" },
  attachMenu: { display: "flex", flexWrap: "wrap", gap: 8, padding: "8px 20px", borderTop: "1px solid #151520" },
  attachItem: { padding: "8px 12px", border: "1px solid #222", background: "transparent", color: "#aaa", fontSize: 12, cursor: "pointer" },
  inputBar: { display: "flex", gap: 10, padding: "14px 20px", borderTop: "1px solid #151520", alignItems: "center" },
  plusBtn: { width: 42, height: 42, border: "1px solid #333", background: "transparent", color: "#00F0FF", fontSize: 22, cursor: "pointer", flexShrink: 0 },
};
