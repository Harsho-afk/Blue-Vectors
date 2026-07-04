import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import ARIACollector from "./components/ARIACollector";

createRoot(document.getElementById("root")).render(
  <StrictMode>
    <ARIACollector />
  </StrictMode>
);
