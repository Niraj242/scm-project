import { useNavigate } from "react-router-dom";
import "./MainDashboard.css";

export default function MainDashboard() {
  const navigate = useNavigate();

  const modules = [

    {
      title: "Transit Buffer Weighing Data",
      desc: "Transit Buffer Entry & Calibration tracking",
      path: "/tbe",
      icon: "T",
    },
    
    {
      title: "MO Traceability",
      desc: "End-to-end manufacturing order tracking",
      path: "/traceability",
      icon: "MO",
    },
    
    {
      title: "Afetr Channel Entries",
      desc: "Dismantling, Rework, Accurate & CPS Entry",
      path: "/afterchannel",
      icon: "AC",
    },

  ];

  return (
    <div className="dashboard-container">
      <header className="dashboard-header">
        <h1>AI-Driven Supply Chain Management System</h1>
        <p>End-to-End Optimization Platform for Manufacturing</p>
      </header>

      <div className="dashboard-grid">
        {modules.map((mod) => (
          <div
            key={mod.path}
            className="dashboard-card"
            onClick={() => navigate(mod.path)}
          >
            <div className="card-icon">{mod.icon}</div>
            <h3>{mod.title}</h3>
            <p>{mod.desc}</p>
          </div>
        ))}
      </div>
    </div>
  );
}
