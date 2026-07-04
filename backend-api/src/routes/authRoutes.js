import express from "express";
import bcrypt from "bcrypt";
import jwt from "jsonwebtoken";
import {pool} from "../db/pool.js";


const router= express.Router()

router.post('/register', async (req,res,next)=>{
    try {
        const {firstname,lastname,email,password} =req.body;


    if (!firstname || !lastname || !email || !password) {
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
        `,[firstname,lastname,email,passwordHash]
    );

    res.status(201).json({
        message: "User created sucessfully",
        user : result.rows[0]
    })


    } catch(error){
        next(error)
    }
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