import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";

import "@fontsource-variable/inter";
import "@fontsource-variable/montserrat";
import "@fontsource-variable/nunito";
import "@fontsource-variable/open-sans";
import "@fontsource-variable/plus-jakarta-sans";
import "@fontsource-variable/roboto";
import "@fontsource-variable/source-sans-3";
import "@fontsource/press-start-2p"; // arcade minigame pixel font

import "katex/dist/katex.min.css";

import "./i18n";
import App from "./App";
import "./index.css";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <BrowserRouter>
      <App />
    </BrowserRouter>
  </React.StrictMode>,
);
