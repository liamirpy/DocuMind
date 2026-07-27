import express from "express";
import cors from "cors";
import cookieParser from "cookie-parser";
import { errorMiddleware } from "./middleware/errorMiddleware.js";
import authRoutes from "./routes/authRoutes.js"
import folderRoutes from "./routes/folderRoutes.js";
import documentRoutes from "./routes/documentRoutes.js";
import ragRoutes from "./routes/ragRoutes.js"

const app = express();

app.use(cors({
  origin: "http://localhost:3000",
  credentials: true
}));

app.use(express.json());



app.get('/api/health',(req,res)=>{
    res.json({
        status: "ok",
        message: "Server is running"
    })
})

app.use(express.json());
app.use(cookieParser());

app.use('/api/auth',authRoutes)
app.use("/api/folders", folderRoutes);
app.use("/api/documents", documentRoutes);

app.use("/api/rag", ragRoutes);

app.use(errorMiddleware);


export default app;