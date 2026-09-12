import { Route, Routes } from "react-router-dom";
import Layout from "./components/Layout";
import DataExplorer from "./pages/DataExplorer";
import Health from "./pages/Health";
import Overview from "./pages/Overview";
import Recovery from "./pages/Recovery";
import Sleep from "./pages/Sleep";
import Strain from "./pages/Strain";
import Stub from "./pages/Stub";
import Trends from "./pages/Trends";

export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<Overview />} />
        <Route path="recovery" element={<Recovery />} />
        <Route path="strain" element={<Strain />} />
        <Route path="sleep" element={<Sleep />} />
        <Route path="health" element={<Health />} />
        <Route path="trends" element={<Trends />} />
        <Route path="activities" element={<DataExplorer />} />
        <Route path="explorer" element={<DataExplorer />} />
        <Route path="*" element={<Stub title="Page not found" />} />
      </Route>
    </Routes>
  );
}
