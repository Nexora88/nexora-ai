"use client";

import { useState, useEffect } from "react";
import axios from "axios";

const API_URL = "http://localhost:8000/api/v1";

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

  const logout = () => {
    localStorage.removeItem("nexora_token");
    setToken(null);
    setMessages([]);
  };

  if (!token) {
    return (
      <div style={{ maxWidth: 400, margin: "80px auto", padding: 24 }}>
        <h1 style={{ textAlign: "center", marginBottom: 8 }}>Nexora AI</h1>
        <p style={{ textAlign: "center", color: "#888", marginBottom: 32 }}>
          Veri • Zekâ • Gelecek
        </p>

        {!isLogin && (
          <input
            placeholder="Ad Soyad"
            value={fullName}
            onChange={(e) => setFullName(e.target.value)}
            style={inputStyle}
          />
        )}
        <input
          placeholder="Email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          style={inputStyle}
        />
        <input
          type="password"
          placeholder="Şifre"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          style={inputStyle}
        />

        {error && <p style={{ color: "#ff6b6b", marginBottom: 12 }}>{error}</p>}

        <button onClick={handleAuth} style={buttonStyle}>
          {isLogin ? "Giriş Yap" : "Kayıt Ol"}
        </button>

        <p
          style={{ textAlign: "center", marginTop: 16, cursor: "pointer", color: "#00f0ff" }}
          onClick={() => setIsLogin(!isLogin)}
        >
          {isLogin ? "Hesabın yok mu? Kayıt ol" : "Zaten hesabın var mı? Giriş yap"}
        </p>
      </div>
    );
  }

  return (
    <div style={{ maxWidth: 800, margin: "0 auto", height: "100vh", display: "flex", flexDirection: "column" }}>
      <header style={{ padding: "16px 24px", borderBottom: "1px solid #222", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <div>
          <strong>Nexora AI</strong>
          {remaining !== null && (
            <span style={{ marginLeft: 12, color: "#888", fontSize: 14 }}>
              Kalan hak: {remaining}
            </span>
          )}
        </div>
        <button onClick={logout} style={{ ...buttonStyle, padding: "6px 14px", fontSize: 14 }}>
          Çıkış
        </button>
      </header>

      <div style={{ flex: 1, overflowY: "auto", padding: 24 }}>
        {messages.length === 0 && (
          <p style={{ color: "#666", textAlign: "center", marginTop: 40 }}>
            Merhaba! Size nasıl yardımcı olabilirim?
          </p>
        )}
        {messages.map((m, i) => (
          <div
            key={i}
            style={{
              marginBottom: 16,
              padding: 12,
              borderRadius: 8,
              background: m.role === "user" ? "#1a1a2e" : "#16213e",
              maxWidth: "85%",
              marginLeft: m.role === "user" ? "auto" : 0,
            }}
          >
            <div style={{ fontSize: 12, color: "#888", marginBottom: 4 }}>
              {m.role === "user" ? "Sen" : "Nexora"}
            </div>
            <div style={{ whiteSpace: "pre-wrap" }}>{m.content}</div>
          </div>
        ))}
        {loading && <p style={{ color: "#888" }}>Düşünüyor...</p>}
      </div>

      {error && <p style={{ color: "#ff6b6b", padding: "0 24px" }}>{error}</p>}

      <div style={{ padding: 16, borderTop: "1px solid #222", display: "flex", gap: 8 }}>
        <input
          value={message}
          onChange={(e) => setMessage(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && !e.shiftKey && sendMessage()}
          placeholder="Mesajını yaz..."
          style={{ ...inputStyle, marginBottom: 0, flex: 1 }}
        />
        <button onClick={sendMessage} disabled={loading} style={buttonStyle}>
          Gönder
        </button>
      </div>
    </div>
  );
}

const inputStyle: React.CSSProperties = {
  width: "100%",
  padding: "12px 16px",
  marginBottom: 12,
  borderRadius: 8,
  border: "1px solid #333",
  background: "#1a1a2e",
  color: "#fff",
  fontSize: 16,
};

const buttonStyle: React.CSSProperties = {
  width: "100%",
  padding: "12px",
  borderRadius: 8,
  border: "none",
  background: "linear-gradient(90deg, #00f0ff, #7b2cff)",
  color: "#000",
  fontWeight: 600,
  cursor: "pointer",
  fontSize: 16,
};
