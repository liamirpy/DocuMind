import dotenv from "dotenv";
import {pool} from "./db/pool.js";
import app from "./app.js";

dotenv.config()
const PORT = process.env.PORT || 8000;


async function startServer() {
  try {
    await pool.query("SELECT NOW()");
    console.log("Database connected");

    app.listen(PORT, () => {
      console.log(`Server running on http://localhost:${PORT}`);
    });
  } catch (error) {
    console.error("Failed to start server:", error);
    process.exit(1);
  }
}

startServer();

