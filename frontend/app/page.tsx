"use client";

import { useState, useEffect } from "react";
import axios from "axios";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1";

export default function Home() {
  const [token, setToken] = useState<string | null>(null);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [fullName, setFullName] = useState("");
  const [isLogin, setIsLogin] = useState(true);
  const [message, setMessage] = useState("");
  const [messages, setMessages] = useState<{ role: string; content: string }[]>([]);
  const [remaining, setRemaining] = useState<number | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [symbol, setSymbol] = useState("");
  const [showMarket, setShowMarket] = useState(false);

  useEffect(() => {
    const saved = localStorage.getItem("nexora_token");
    if (saved) setToken(saved);
  }, []);

  const handleAuth = async () => {
    setError("");
    try {
      if (isLogin) {
        const res = await axios.post(`${API_URL}/auth/login`, { email, password });
        localStorage.setItem("nexora_token", res.data.access_token);
        setToken(res.data.access_token);
      } else {
        await axios.post(`${API_URL}/auth/register`, {
          email,
          password,
          full_name: fullName,
        });
        setIsLogin(true);
        setError("Kayıt başarılı! Şimdi giriş yap.");
      }
    } catch (err: any) {
      setError(err.response?.data?.detail || "Bir hata oluştu");
    }
  };

  const sendMessage = async () => {
    if (!message.trim() || !token) return;
    setLoading(true);
    setError("");

    const newMessages = [...messages, { role: "user", content: message }];
    setMessages(newMessages);
    setMessage("");

    try {
      const res = await axios.post(
        `${API_URL}/chat`,
        {
          messages: newMessages.map((m) => ({ role: m.role, content: m.content })),
          stream: false,
        },
        { headers: { Authorization: `Bearer ${token}` } }
      );

      setMessages([...newMessages, { role: "assistant", content: res.data.content }]);
      setRemaining(res.data.remaining);
    } catch (err: any) {
      setError(err.response?.data?.detail || "Mesaj gönderilemedi");
    } finally {
      setLoading(false);
    }
  };

  const analyzeMarket = async () => {
    if (!symbol.trim() || !token) return;
    setLoading(true);
    setError("");
    setShowMarket(false);

    try {
      const res = await axios.post(
        `${API_URL}/market/analyze`,
        { symbol: symbol.trim() },
        { headers: { Authorization: `Bearer ${token}` } }
      );

      const analysis = `📊 **${res.data.symbol} Analizi**\n\n${res.data.analysis}`;
      setMessages((prev) => [...prev, { role: "assistant", content: analysis }]);
    } catch (err: any) {
      setError(err.response?.data?.detail || "Analiz yapılamadı");
    } finally {
      setLoading(false);
      setSymbol("");
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
      if (res.data.checkout_url) {
        window.location.href = res.data.checkout_url;
      }
    } catch (err: any) {
      setError(err.response?.data?.detail || "Ödeme başlatılamadı");
    }
  };

  const logout = () => {
    localStorage.removeItem("nexora_token");
    setToken(null);
    setMessages([]);
  };

  if (!token) {
    return (
      <div style={{ maxWidth: 400, margin: "80px auto", padding: 24 }}>
        <h1 style={{ textAlign: "center", marginBottom: 8, background: "linear-gradient(90deg, #00f0ff, #7b2cff)", WebkitBackgroundClip: "text", color: "transparent" }}>
          Nexora AI
        </h1>
        <p style={{ textAlign: "center", color: "#888", marginBottom: 32 }}>
          Veri • Zekâ • Gelecek
        </p>

        {!isLogin && (
          <input placeholder="Ad Soyad" value={fullName} onChange={(e) => setFullName(e.target.value)} style={inputStyle} />
        )}
        <input placeholder="Email" value={email} onChange={(e) => setEmail(e.target.value)} style={inputStyle} />
        <input type="password" placeholder="Şifre" value={password} onChange={(e) => setPassword(e.target.value)} style={inputStyle} />

        {error && <p style={{ color: "#ff6b6b", marginBottom: 12 }}>{error}</p>}

        <button onClick={handleAuth} style={buttonStyle}>
          {isLogin ? "Giriş Yap" : "Kayıt Ol"}
        </button>

        <p style={{ textAlign: "center", marginTop: 16, cursor: "pointer", color: "#00f0ff" }} onClick={() => setIsLogin(!isLogin)}>
          {isLogin ? "Hesabın yok mu? Kayıt ol" : "Zaten hesabın var mı? Giriş yap"}
        </p>
      </div>
    );
  }

  return (
    <div style={{ maxWidth: 800, margin: "0 auto", height: "100vh", display: "flex", flexDirection: "column" }}>
      {/* Header */}
      <header style={{ padding: "14px 20px", borderBottom: "1px solid #222", display: "flex", justifyContent: "space-between", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
        <div>
          <strong style={{ fontSize: 18 }}>Nexora AI</strong>
          {remaining !== null && (
            <span style={{ marginLeft: 10, color: "#888", fontSize: 13 }}>Kalan: {remaining}</span>
          )}
        </div>
        <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
          <button onClick={() => setShowMarket(!showMarket)} style={{ ...smallBtn, background: "#1a1a2e" }}>
            📊 Borsa
          </button>
          <button onClick={() => upgrade("pro")} style={smallBtn}>Pro $12</button>
          <button onClick={() => upgrade("elite")} style={{ ...smallBtn, background: "linear-gradient(90deg, #7b2cff, #ff00aa)" }}>Elite $29</button>
          <button onClick={logout} style={{ ...smallBtn, background: "#333", color: "#fff" }}>Çıkış</button>
        </div>
      </header>

      {/* Borsa Kutusu */}
      {showMarket && (
        <div style={{ padding: "12px 20px", background: "#111", borderBottom: "1px solid #222", display: "flex", gap: 8 }}>
          <input
            value={symbol}
            onChange={(e) => setSymbol(e.target.value)}
            placeholder="Sembol gir (BTC, ETH, SOL...)"
            style={{ ...inputStyle, marginBottom: 0, flex: 1 }}
            onKeyDown={(e) => e.key === "Enter" && analyzeMarket()}
          />
          <button onClick={analyzeMarket} disabled={loading} style={{ ...buttonStyle, width: "auto", padding: "10px 16px" }}>
            Analiz Et
          </button>
        </div>
      )}

      {/* Mesajlar */}
      <div style={{ flex: 1, overflowY: "auto", padding: 20 }}>
        {messages.length === 0 && (
          <p style={{ color: "#555", textAlign: "center", marginTop: 60 }}>
            Merhaba! Sohbet edebilir veya yukarıdan borsa analizi yapabilirsin.
          </p>
        )}
        {messages.map((m, i) => (
          <div
            key={i}
            style={{
              marginBottom: 14,
              padding: 12,
              borderRadius: 10,
              background: m.role === "user" ? "#1a1a2e" : "#16213e",
              maxWidth: "88%",
              marginLeft: m.role === "user" ? "auto" : 0,
            }}
          >
            <div style={{ fontSize: 11, color: "#777", marginBottom: 4 }}>
              {m.role === "user" ? "Sen" : "Nexora"}
            </div>
            <div style={{ whiteSpace: "pre-wrap", lineHeight: 1.5 }}>{m.content}</div>
          </div>
        ))}
        {loading && <p style={{ color: "#888" }}>Düşünüyor...</p>}
      </div>

      {error && <p style={{ color: "#ff6b6b", padding: "0 20px 8px" }}>{error}</p>}

      {/* Input */}
      <div style={{ padding: 14, borderTop: "1px solid #222", display: "flex", gap: 8 }}>
        <input
          value={message}
          onChange={(e) => setMessage(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && !e.shiftKey && sendMessage()}
          placeholder="Mesajını yaz..."
          style={{ ...inputStyle, marginBottom: 0, flex: 1 }}
        />
        <button onClick={sendMessage} disabled={loading} style={{ ...buttonStyle, width: "auto", padding: "12px 18px" }}>
          Gönder
        </button>
      </div>
    </div>
  );
}

const inputStyle: React.CSSProperties = {
  width: "100%",
  padding: "11px 14px",
  marginBottom: 10,
  borderRadius: 8,
  border: "1px solid #333",
  background: "#1a1a2e",
  color: "#fff",
  fontSize: 15,
};

const buttonStyle: React.CSSProperties = {
  padding: "11px 16px",
  borderRadius: 8,
  border: "none",
  background: "linear-gradient(90deg, #00f0ff, #7b2cff)",
  color: "#000",
  fontWeight: 600,
  cursor: "pointer",
  fontSize: 15,
};

const smallBtn: React.CSSProperties = {
  padding: "6px 11px",
  borderRadius: 6,
  border: "none",
  background: "linear-gradient(90deg, #00f0ff, #7b2cff)",
  color: "#000",
  fontWeight: 600,
  cursor: "pointer",
  fontSize: 12,
};
