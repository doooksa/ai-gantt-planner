import ReactDOM from "react-dom/client";

import App from "./App";
import "./styles.css";

// Note: no React.StrictMode — the SVAR Gantt widget double-initialises under
// StrictMode's dev double-invoke, which duplicates its event listeners.
ReactDOM.createRoot(document.getElementById("root")!).render(<App />);
