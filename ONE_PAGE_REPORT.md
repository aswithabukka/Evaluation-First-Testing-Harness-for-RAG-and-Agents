# Weekly Progress Report

**Project:** Evaluation-First Testing Harness for RAG and AI Agents
**Student:** Aswitha Bukka
**Date:** February 25, 2026

---

## Project Overview

AI-powered applications — such as RAG pipelines, tool-calling agents, and chatbots — fail silently. A model update can introduce hallucinations, a prompt change can degrade answer quality, and an agent can start invoking wrong APIs, all without producing any visible errors. This project builds an **evaluation harness** that automatically scores, gates, and monitors these AI systems before they reach production, treating LLM evaluation as a first-class CI/CD concern.

## Work Completed This Week

### Research and Exploration

I conducted research into modern AI agent architectures and agentic tooling to inform the design of the evaluation harness. A major area of focus was **OpenClaw** (openclaw.ai), an open-source, local-first autonomous AI agent. I set up OpenClaw locally and studied its architecture hands-on — how it orchestrates tool-calling decisions, manages persistent memory across sessions, routes conversations across multiple messaging platforms (Slack, WhatsApp, Telegram, Discord), and handles browser automation with configurable sandboxing. I also explored its plugin system, which supports 50+ integrations and allows the agent to dynamically build its own skills at runtime.

This research directly shaped the evaluation harness design. OpenClaw's multi-platform message routing informed the **multi-turn chatbot evaluator** (tracking coherence and knowledge retention across conversation turns). Its autonomous tool selection logic informed the **tool-calling agent evaluator** (measuring tool call precision, argument accuracy, and step efficiency). Its extensible plugin architecture inspired the **dynamic adapter pattern** used in the harness, where pipeline adapters are loaded at runtime via configuration rather than hard-coded.

I also researched evaluation frameworks (Ragas, DeepEval), LLM-as-Judge patterns using GPT-4o, and production monitoring strategies for AI systems — synthesizing findings from multiple sources to build a comprehensive evaluation approach.

### Development

Using insights from the research phase, I built and deployed the full evaluation platform:

- **Backend**: FastAPI server with 25+ REST endpoints, Celery distributed task queue, PostgreSQL with JSONB-based flexible metric storage, and Redis as the message broker — supporting 4 AI system types and 13 evaluators.
- **Seven new features implemented**: Slack/Webhook Alerts (rich Block Kit notifications on quality gate failures), CSV/JSON Export (full evaluation result downloads), User Feedback Collection (thumbs up/down ratings with aggregated statistics), LLM-Powered Test Case Generation (GPT-4o generates system-type-specific test cases), Side-by-Side Run Comparison (compare 2-4 evaluation runs visually), Multi-Model A/B Testing (batch-trigger runs across different model configurations), and Dark Mode.
- **Frontend**: Next.js 14 dashboard with 10 pages, real-time data polling, interactive metric visualizations, and a playground for live AI system testing.
- **Infrastructure**: 6 Docker containers orchestrated via Docker Compose, with GitHub Actions CI/CD pipelines.

In total, 26 files were modified with over 1,300 lines of code added.

## Key Takeaway

Working with OpenClaw gave me a practitioner's understanding of how autonomous AI agents operate in real-world settings — managing state, making tool-calling decisions, integrating with external systems, and operating within safety boundaries. This hands-on experience directly informed the metrics, evaluators, and architectural decisions in the evaluation harness, ensuring it tests the exact failure modes that production AI systems actually exhibit.

## Technologies Used

Python, FastAPI, PostgreSQL, Redis, Celery, Next.js, TypeScript, Tailwind CSS, OpenAI GPT-4o, Ragas, Docker, GitHub Actions, OpenClaw
