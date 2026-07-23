import express from "express";
import bcrypt from "bcrypt";
import crypto from "node:crypto";
import jwt from "jsonwebtoken";
import {pool} from "../db/pool.js";
import {authMiddleware} from "../middleware/authMiddleware.js";

const router= express.Router()

router.post('/register', async (req,res,next)=>{
    try {
        const {first_name,last_name,email,password} =req.body;


    if (!first_name || !last_name || !email || !password) {
            return res.status(400).json({
            error: "First name, last name and password are required"
        });

    }

    if (password.length <8) {
        return res.status(400).json({
            error: "Password must be at least 8 characters"
        });
    }

    const existingUser= await pool.query(
        `SELECT id FROM users WHERE email = $1`,
        [email]
    )
    if (existingUser.rowCount > 0){
        return res.status(409).json({
            error: "Email already exist"
        });
    }

    const passwordHash= await bcrypt.hash(password,12);

    const result= await pool.query(
        `
        INSERT INTO users(first_name,last_name,email,password_hash)
        VALUES ($1, $2, $3,$4)
        RETURNING  id,first_name,last_name,email,created_at
        `,[first_name,last_name,email,passwordHash]
    );

    res.status(201).json({
        message: "User created sucessfully",
        user : result.rows[0]
    })


    } catch(error){
        next(error)
    }
});



router.post('/login', async (req,res,next)=>{
    try {
        const {email,password} = req.body;

        if (!email || !password) {
            return res.status(400).json({
                error: "Email and password are required"
            });
        }


        
        const userResult= await pool.query(
            `SELECT id,first_name,last_name,email,password_hash FROM users WHERE email = $1`,
            [email]
        );

        if (userResult.rowCount === 0){
            return res.status(401).json({
                error: "Invalid email or password"
            });
        }

        const user= userResult.rows[0];

        const isPasswordValid= await bcrypt.compare(password,user.password_hash);

        if (!isPasswordValid){
            return res.status(401).json({
                error: "Invalid email or password"
            });
        }

        

        const refreshToken= crypto.randomBytes(64).toString('hex');

        const refreshTokenHash= crypto
        .createHash('sha256')
        .update(refreshToken)
        .digest('hex');

        const sessionResult = await pool.query(
            `INSERT INTO user_sessions(user_id,refresh_token_hash,expires_at) 
            VALUES ($1,$2,NOW() + INTERVAL '30 days')
            RETURNING id `,
            [user.id, refreshTokenHash]
        );

        const accessToken= jwt.sign(
            {user_id: user.id,
                session_id: sessionResult.rows[0].id
        },
        process.env.JWT_SECRET,
        {expiresIn: '45 minutes'}
        );



        res.cookie('refreshToken',refreshToken,{
            httpOnly: true,
            secure: false,
            sameSite: 'strict',
            path: "/",
            maxAge: 30 * 24 * 60 * 60 * 1000
        });


        res.status(200).json({
            message: "Login successful",
            accessToken,
            user: {
                id: user.id,
                first_name: user.first_name,
                last_name: user.last_name,
                email: user.email
            } 
        });

    } catch(error){
        next(error)
    }
});



router.post('/refresh-token', async (req,res,next)=>{
    try {
        const refreshToken = req.cookies.refreshToken;



        if (!refreshToken){
            return res.status(401).json({
                error: "Refresh token is required"
            });
        }

        const refreshTokenHash= crypto
        .createHash('sha256')
        .update(refreshToken)
        .digest('hex'); 

       const sessionResult = await pool.query(
            `
            SELECT 
                user_sessions.id AS session_id,
                user_sessions.user_id,
                user_sessions.expires_at,
                users.first_name,
                users.last_name,
                users.email
            FROM user_sessions
            JOIN users ON users.id = user_sessions.user_id
            WHERE user_sessions.refresh_token_hash = $1
              AND user_sessions.expires_at > NOW()
            `,
            [refreshTokenHash]
        );

        const session = sessionResult.rows[0];

        if (sessionResult.rowCount === 0){
            res.clearCookie('refreshToken', {
                httpOnly: true,
                secure: false,
                sameSite: 'strict',
                path: "/",

            });
            return res.status(401).json({
                error: "Invalid or expired refresh token"
            });
        }


        const userId= sessionResult.rows[0].user_id;
        const sessionId= sessionResult.rows[0].session_id;

        const accessToken = jwt.sign(
            {
                user_id: session.user_id,
                session_id: session.session_id
            },
            process.env.JWT_SECRET,
            { expiresIn: "15 minutes" }
            );

        const newRefreshToken= crypto.randomBytes(64).toString('hex');

        const newRefreshTokenHash= crypto
        .createHash('sha256')
        .update(newRefreshToken)
        .digest('hex');

        // console.log("New Refresh Token :", newRefreshToken);


        await pool.query(
            `UPDATE user_sessions
             SET refresh_token_hash = $1, expires_at = NOW() + INTERVAL '30 days' 
             WHERE id = $2`,
            [newRefreshTokenHash,session.session_id]
        );

        // console.log("Incoming cookies:", req.cookies);
        // console.log("Incoming refreshToken:", req.cookies.refreshToken);

        res.cookie('refreshToken',newRefreshToken,{
            httpOnly: true,
            secure: false,
            sameSite: 'strict',
              path: "/",
            maxAge: 30 * 24 * 60 * 60 * 1000

        });

        res.status(200).json({
            message: "Access token refreshed successfully",
            accessToken,
            user: {
                id: sessionResult.rows[0].user_id,
                first_name: sessionResult.rows[0].first_name,
                last_name: sessionResult.rows[0].last_name,
                email: sessionResult.rows[0].email
            }
        });

    } catch(error){
        next(error)
    }
});



router.post('/logout', async (req,res,next)=>{
    try {
        const refreshToken = req.cookies.refreshToken;

        if (!refreshToken){
            return res.status(400).json({
                error: "Refresh token is required"
            });
        }

        const refreshTokenHash= crypto
        .createHash('sha256')
        .update(refreshToken)
        .digest('hex');

        await pool.query(
            `UpDATE user_sessions
            SET revoked_at= NOW()
            WHERE refresh_token_hash = $1`,
            [refreshTokenHash]
        );

        res.clearCookie('refreshToken', {
            httpOnly: true,
            secure: false,
            sameSite: 'strict',
            path: "/",

        });

        res.status(200).json({
            message: "Logout successful"
        });
        
    } catch(error){
        next(error)
    }
}); 



router.get("/me", authMiddleware, async (req, res) => {
  res.json({
    user: {
      id: req.user.id,
      first_name: req.user.first_name,
      last_name: req.user.last_name,
      email: req.user.email
    }
  });
});



export default router;




// curl -X POST http://localhost:8001/api/auth/register \
//   -H "Content-Type: application/json" \
//   -d '{
//     "firstname": "Amir",
//     "lastname": "Mousavi",
//     "email": "amir@test.com",
//     "password": "password123"
//   }'