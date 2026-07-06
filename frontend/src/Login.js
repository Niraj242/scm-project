import { useNavigate } from "react-router-dom";
import { useState, useEffect } from "react";
import "./Login.css";


const API_BASE_URL = process.env.REACT_APP_API_URL || "http://127.0.0.1:8000";

function Login() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");

  const navigate = useNavigate();

  useEffect(() => {
    localStorage.removeItem("token");
    localStorage.removeItem("role");
  }, []);

  const handleLogin = async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/login`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          email,
          password,
        }),
      });

      const data = await response.json();

      if (response.ok) {
        sessionStorage.setItem("token", data.access_token || data.token);
        sessionStorage.setItem("role", data.role || "admin");

        navigate("/dashboard");
      } else {
        alert(data.detail || "Invalid email or password");
      }
    } catch (error) {
      alert("Error connecting to server");
    }
  };

 return (
  <div className="login-page">

    <div className="login-left">

      <div className="brand-box">

        <img
          src="/skf-logo.png"
          alt="SKF Logo"
          className="skf-logo"
        />
        <h2>AI Driven Supply Chain Management</h2>
        
        <p>
          Intelligent Manufacturing • Traceability • Transit Buffer •
          Production Monitoring • Analytics
        </p>

      </div>

    </div>

      <div className="login-right">

        <div className="login-card">

          <h2>Welcome Back</h2>

          <p>Please login to continue</p>

          <input
            type="email"
            placeholder="Email Address"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />

          <input
            type="password"
            placeholder="Password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />

          <button onClick={handleLogin}>
            Login
          </button>

        </div>

      </div>

    </div>
  );
}

export default Login;