
import { createRoot } from "react-dom/client";
import App from "./app/App";
import { AppErrorBoundary } from "./app/components/AppErrorBoundary";
import { clearRecentDestinationHistory } from "./utils/kioskStorage";
import "./styles/index.css";

clearRecentDestinationHistory();

const root = document.getElementById("root");
if (!root) throw new Error("Application root element is missing.");

createRoot(root).render(
  <AppErrorBoundary>
    <App />
  </AppErrorBoundary>,
);
