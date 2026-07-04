import express from "express";
import cors from "cors";
import { errorMiddleware } from "./middleware/errorMiddleware.js";
import authRoutes from "./routes/authRoutes.js"
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

app.use('/api/auth',authRoutes)

app.use(errorMiddleware);


export default app;