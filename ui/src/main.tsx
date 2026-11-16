import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./shell/App";
import "./shell/base.css";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
