---
name: Frontend
description: Rules for changes under frontend/ (Next.js 14, TypeScript).
applyTo: frontend/**
---

# Frontend

- Next.js 14 App Router. Add `"use client"` only to interactive components.
- TypeScript strict is on. Do not add `any` to silence the compiler.
- Do not add a dependency without confirming the need with Sam.
- Before you finish, run: `cd frontend && npm run typecheck && npm run build`