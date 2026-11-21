import React from "react"; import ReactDOM from "react-dom/client"; import { BrowserRouter } from "react-router-dom";
import App from "./App"; import "./styles.css";
document.documentElement.dataset.theme = localStorage.getItem("theme") || "dark";
ReactDOM.createRoot(document.getElementById("root")!).render(<BrowserRouter><App /></BrowserRouter>);
