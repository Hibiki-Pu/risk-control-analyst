import { Navigate, Route, Routes } from "react-router-dom";

import { AppShell } from "@/components/AppLayout";
import AiAnalyst from "@/pages/AiAnalyst";
import MarketIntelligence from "@/pages/MarketIntelligence";
import Overview from "@/pages/Overview";
import PnlAnalysis from "@/pages/PnlAnalysis";
import ReportCenter from "@/pages/ReportCenter";
import RiskControl from "@/pages/RiskControl";
import ScenarioSimulator from "@/pages/ScenarioSimulator";

export default function App() {
  return (
    <Routes>
      <Route element={<AppShell />}>
        <Route path="/" element={<Overview />} />
        <Route path="/pnl" element={<PnlAnalysis />} />
        <Route path="/risk" element={<RiskControl />} />
        <Route path="/market" element={<MarketIntelligence />} />
        <Route path="/scenarios" element={<ScenarioSimulator />} />
        <Route path="/analyst" element={<AiAnalyst />} />
        <Route path="/reports" element={<ReportCenter />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  );
}
