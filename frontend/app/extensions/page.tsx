"use client";

import { useCallback, useEffect, useState } from "react";
import axios from "axios";
import { useRouter } from "next/navigation";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1";

type Repo = { full_name: string; private?: boolean; default_branch?: string };
type Grant = { plugin: string; scope: string; mode: string };

export default function ExtensionsPage() {
  const router = useRouter();
  const [token, setToken] = useState<string | null>(null);
  const [status, setStatus] = useState<any>(null);
  const [repos, setRepos] = useState<Repo[]>([]);
  const [selected, setSelected] = useState("");
  const [grants, setGrants] = useState<Grant[]>([]);
  const [indexStats, setIndexStats] = useState<any>(null);
  const [searchQ, setSearchQ] = useState("");
  const [searchHits, setSearchHits] = useState<any[]>([]);
  const [msg, setMsg] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  const headers = (t: string) => ({ Authorization: `Bearer ${t}` });

  const load = useCallback(async (t: string) => {
    setErr("");
    try {
      const st = await axios.get(`${API}/ship/status`, { headers: headers(t) });
      setStatus(st.data);
      if (st.data.connected) {
        const rp = await axios.get(`${API}/ship/repos`, { headers: headers(t) });
        setRepos(rp.data.repos || []);
        setSelected(rp.data.default_repo || st.data.default_repo || "");
        try {
          const ix = await axios.get(`${API}/plugins/index`, { headers: headers(t) });
          setIndexStats(ix.data.cached ? ix.data.stats : null);
        } catch {
          setIndexStats(null);
        }
      }
      try {
        const g = await axios.get(`${API}/permissions`, { headers: headers(t) });
        setGrants(g.data.grants || []);
      } catch {
        setGrants([]);
      }
    } catch (e: any) {
      setErr(e.response?.data?.detail || "Yüklenemedi");
    }
  }, []);

  useEffect(() => {
    const t = localStorage.getItem("nexora_token");
    if (!t) {
      router.push("/");
      return;
    }
    setToken(t);
    load(t);
  }, [router, load]);

  const connect = async () => {
    if (!token) return;
    setBusy(true);
    try {
      const res = await axios.get(`${API}/ship/connect`, { headers: headers(token) });
      window.location.href = res.data.authorize_url;
    } catch (e: any) {
      setErr(e.response?.data?.detail || "OAuth başlatılamadı");
      setBusy(false);
    }
  };

  const saveRepo = async () => {
    if (!token || !selected) return;
    setBusy(true);
    setMsg("");
    try {
      await axios.post(
        `${API}/ship/default-repo`,
        { repo: selected },
        { headers: headers(token) }
      );
      setMsg(`Repo kaydedildi: ${selected}`);
      await load(token);
    } catch (e: any) {
      setErr(e.response?.data?.detail || "Repo kaydedilemedi");
    } finally {
      setBusy(false);
    }
  };

  const disconnect = async () => {
    if (!token) return;
    setBusy(true);
    try {
      await axios.delete(`${API}/ship/disconnect`, { headers: headers(token) });
      setIndexStats(null);
      setSearchHits([]);
      await load(token);
      setMsg("GitHub bağlantısı kesildi");
    } catch (e: any) {
      setErr(e.response?.data?.detail || "Kesilemedi");
    } finally {
      setBusy(false);
    }
  };

  const setGrant = async (plugin: string, mode: string) => {
    if (!token) return;
    const scope = selected || "*";
    try {
      await axios.put(
        `${API}/permissions`,
        { plugin, scope, mode },
        { headers: headers(token) }
      );
      setMsg(`İzin: ${plugin} → ${mode}`);
      await load(token);
    } catch (e: any) {
      setErr(e.response?.data?.detail || "İzin kaydedilemedi");
    }
  };

  const buildIndex = async () => {
    if (!token) return;
    setBusy(true);
    setMsg("İndeksleniyor…");
    setErr("");
    try {
      const res = await axios.post(`${API}/plugins/index`, {}, { headers: headers(token) });
      if (res.data.needs_prompt) {
        setErr(res.data.message || "İzin gerekli");
        setMsg("");
        return;
      }
      setIndexStats(res.data.stats);
      setMsg(
        `Index hazır · ${res.data.stats?.file_count ?? 0} dosya · ${res.data.stats?.symbol_count ?? 0} sembol`
      );
    } catch (e: any) {
      setErr(e.response?.data?.detail || "Index başarısız");
      setMsg("");
    } finally {
      setBusy(false);
    }
  };

  const runSearch = async () => {
    if (!token || !searchQ.trim()) return;
    setBusy(true);
    try {
      const res = await axios.get(`${API}/plugins/index/search`, {
        headers: headers(token),
        params: { q: searchQ.trim() },
      });
      setSearchHits(res.data.hits || []);
      setMsg(`Arama: ${res.data.hits?.length ?? 0} sonuç`);
    } catch (e: any) {
      setErr(e.response?.data?.detail || "Arama başarısız — önce indeksle");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div style={s.page}>
      <header style={s.header}>
        <div style={s.brand} onClick={() => router.push("/")}>
          NEXORA
        </div>
        <div style={s.sub}>EKLENTİLER</div>
        <button type="button" style={s.ghost} onClick={() => router.push("/")}>
          Core
        </button>
      </header>

      <main style={s.main}>
        <h1 style={s.title}>Eklentiler</h1>
        <p style={s.desc}>
          GitHub Ship, izinler ve dinamik repo indeksi. Arka planda ajanlar çalışırken
          burada bağlantı ve kapsam yönetilir.
        </p>

        {err && <div style={s.error}>{String(err)}</div>}
        {msg && <div style={s.ok}>{msg}</div>}

        {/* GitHub Ship */}
        <section style={s.card}>
          <div style={s.cardTop}>
            <div>
              <div style={s.cardTitle}>GitHub Ship</div>
              <div style={s.meta}>
                {status?.connected
                  ? `Bağlı · @${status.github_username || "user"}`
                  : "Bağlı değil"}
                {" · "}
                {status?.ship_token_cost ?? 10} token / ship
              </div>
            </div>
            {!status?.connected ? (
              <button
                type="button"
                style={s.primary}
                onClick={connect}
                disabled={busy || !status?.oauth_ready}
              >
                Kur
              </button>
            ) : (
              <button type="button" style={s.ghost} onClick={disconnect} disabled={busy}>
                Kes
              </button>
            )}
          </div>

          {!status?.oauth_ready && (
            <div style={s.warn}>
              Sunucuda GITHUB_CLIENT_ID / SECRET yok. .env’e ekle, OAuth App oluştur.
            </div>
          )}

          {status?.connected && (
            <div style={s.block}>
              <div style={s.label}>Varsayılan repo</div>
              <select
                style={s.select}
                value={selected}
                onChange={(e) => setSelected(e.target.value)}
              >
                <option value="">Seç…</option>
                {repos.map((r) => (
                  <option key={r.full_name} value={r.full_name}>
                    {r.full_name}
                    {r.private ? " (private)" : ""}
                  </option>
                ))}
              </select>
              <button
                type="button"
                style={s.primary}
                onClick={saveRepo}
                disabled={!selected || busy}
              >
                Kaydet
              </button>
            </div>
          )}
        </section>

        {/* İzinler */}
        <section style={s.card}>
          <div style={s.cardTitle}>İzinler</div>
          <div style={s.meta}>
            Ship ve index için: her zaman / her seferinde sor / reddet
          </div>
          <div style={s.grantRow}>
            <span style={s.grantName}>github_ship</span>
            <button type="button" style={s.chip} onClick={() => setGrant("github_ship", "always")}>
              Her zaman
            </button>
            <button type="button" style={s.chip} onClick={() => setGrant("github_ship", "ask")}>
              Sor
            </button>
            <button type="button" style={s.chip} onClick={() => setGrant("github_ship", "deny")}>
              Reddet
            </button>
          </div>
          <div style={s.grantRow}>
            <span style={s.grantName}>repo_memory</span>
            <button type="button" style={s.chip} onClick={() => setGrant("repo_memory", "always")}>
              Her zaman
            </button>
            <button type="button" style={s.chip} onClick={() => setGrant("repo_memory", "ask")}>
              Sor
            </button>
            <button type="button" style={s.chip} onClick={() => setGrant("repo_memory", "deny")}>
              Reddet
            </button>
          </div>
          {grants.length > 0 && (
            <div style={s.meta}>
              Kayıtlı:{" "}
              {grants.map((g) => `${g.plugin}:${g.scope}=${g.mode}`).join(" · ")}
            </div>
          )}
        </section>

        {/* Code Index */}
        <section style={s.card}>
          <div style={s.cardTop}>
            <div>
              <div style={s.cardTitle}>Repo Index</div>
              <div style={s.meta}>
                {indexStats
                  ? `${indexStats.file_count} dosya · ${indexStats.symbol_count} sembol · ${indexStats.branch}`
                  : "Henüz indekslenmedi"}
              </div>
            </div>
            <button
              type="button"
              style={s.primary}
              onClick={buildIndex}
              disabled={busy || !status?.connected || !selected}
            >
              {busy ? "…" : "İndeksle"}
            </button>
          </div>
          <div style={s.searchRow}>
            <input
              style={s.input}
              placeholder="Fonksiyon, dosya, sembol ara…"
              value={searchQ}
              onChange={(e) => setSearchQ(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && runSearch()}
            />
            <button type="button" style={s.primary} onClick={runSearch} disabled={busy}>
              Ara
            </button>
          </div>
          {searchHits.length > 0 && (
            <ul style={s.hitList}>
              {searchHits.map((h) => (
                <li key={h.path} style={s.hit}>
                  <strong>{h.path}</strong>
                  <span style={s.meta}>
                    {" "}
                    score {h.score}
                    {h.symbols?.length ? ` · ${h.symbols.slice(0, 4).join(", ")}` : ""}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </section>

        <p style={s.foot}>
          Ship adımları (PM → Coder → QA) sohbet / Core üzerinden; burada bağlantı ve izin.
        </p>
      </main>
    </div>
  );
}

const s: Record<string, React.CSSProperties> = {
  page: {
    minHeight: "100vh",
    background: "#0D0D1A",
    color: "#e0e0e0",
    fontFamily: "system-ui, sans-serif",
  },
  header: {
    display: "flex",
    alignItems: "center",
    gap: 16,
    padding: "14px 20px",
    borderBottom: "1px solid #151520",
  },
  brand: { fontWeight: 700, letterSpacing: 3, cursor: "pointer" },
  sub: { fontSize: 11, color: "#00F0FF", letterSpacing: 2 },
  ghost: {
    marginLeft: "auto",
    padding: "8px 12px",
    border: "1px solid #333",
    background: "transparent",
    color: "#aaa",
    cursor: "pointer",
  },
  main: { maxWidth: 640, margin: "0 auto", padding: 24 },
  title: { fontSize: 22, letterSpacing: 2, fontWeight: 600 },
  desc: { color: "#777", fontSize: 14, lineHeight: 1.5, marginTop: 8, marginBottom: 24 },
  card: {
    border: "1px solid #1a1a2e",
    padding: 20,
    background: "#0a0a12",
    marginBottom: 16,
  },
  cardTop: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "flex-start",
    gap: 12,
    flexWrap: "wrap",
  },
  cardTitle: { fontSize: 16, fontWeight: 600 },
  meta: { fontSize: 12, color: "#666", marginTop: 4 },
  primary: {
    padding: "10px 16px",
    border: "1px solid #00F0FF",
    background: "transparent",
    color: "#00F0FF",
    fontWeight: 600,
    cursor: "pointer",
  },
  block: { marginTop: 16, display: "flex", flexDirection: "column", gap: 10 },
  label: { fontSize: 11, letterSpacing: 1, color: "#666" },
  select: {
    padding: 12,
    background: "#000",
    color: "#eee",
    border: "1px solid #333",
  },
  input: {
    flex: 1,
    padding: 12,
    background: "#000",
    color: "#eee",
    border: "1px solid #333",
  },
  searchRow: { display: "flex", gap: 8, marginTop: 14 },
  grantRow: {
    display: "flex",
    flexWrap: "wrap",
    alignItems: "center",
    gap: 8,
    marginTop: 12,
  },
  grantName: { fontSize: 12, color: "#00F0FF", minWidth: 100 },
  chip: {
    padding: "6px 10px",
    border: "1px solid #333",
    background: "transparent",
    color: "#aaa",
    fontSize: 11,
    cursor: "pointer",
  },
  hitList: { listStyle: "none", padding: 0, marginTop: 12 },
  hit: {
    padding: "8px 0",
    borderBottom: "1px solid #151520",
    fontSize: 13,
  },
  ok: { color: "#00F0FF", fontSize: 13, marginBottom: 12 },
  warn: { marginTop: 12, fontSize: 12, color: "#ffaa66" },
  error: { color: "#ff4466", marginBottom: 12, fontSize: 13 },
  foot: { fontSize: 11, color: "#444", marginTop: 8 },
};
