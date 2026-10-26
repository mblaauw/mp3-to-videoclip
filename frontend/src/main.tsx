import React from "react";
import ReactDOM from "react-dom/client";
import "@fontsource-variable/schibsted-grotesk";
import "./styles/tokens.css";
import "./styles.css";
import "./ui/ui.css";
import { App } from "./App";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);