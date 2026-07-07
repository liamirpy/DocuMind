import jwt from "jsonwebtoken";
import { pool } from "../db/pool.js";

export async function authMiddleware(req, res, next) {
  try {
    const authHeader = req.headers.authorization;

    if (!authHeader || !authHeader.startsWith("Bearer ")) {
      return res.status(401).json({
        error: "Authentication required"
      });
    }

    const token = authHeader.split(" ")[1];

    let decoded;

    try {
      decoded = jwt.verify(token, process.env.JWT_SECRET);
    } catch (error) {
      return res.status(401).json({
        error: "Invalid or expired token"
      });
    }

    console.log("Decoded token:", decoded);

    // Your access token must contain both:
    // {
    //   user_id: user.id,
    //   session_id: sessionId
    // }
    if (!decoded.user_id || !decoded.session_id) {
      return res.status(401).json({
        error: "Invalid token payload"
      });
    }

    const sessionResult = await pool.query(
      `
      SELECT
        s.id AS session_id,
        s.user_id,
        s.expires_at,
        s.revoked_at,
        u.email,
        u.first_name,
        u.last_name
      FROM user_sessions s
      JOIN users u ON u.id = s.user_id
      WHERE s.id = $1
        AND s.user_id = $2
      `,
      [decoded.session_id, decoded.user_id]
    );

    if (sessionResult.rowCount === 0) {
      return res.status(401).json({
        error: "Session not found"
      });
    }

    const session = sessionResult.rows[0];

    if (session.revoked_at) {
      return res.status(401).json({
        error: "Session has been revoked"
      });
    }

    if (new Date(session.expires_at) < new Date()) {
      return res.status(401).json({
        error: "Session expired. Please log in again."
      });
    }

    req.user = {
      id: session.user_id,
      email: session.email,
      first_name: session.first_name,
      last_name: session.last_name,
      session_id: session.session_id
    };

    next();
  } catch (error) {
    next(error);
  }
}