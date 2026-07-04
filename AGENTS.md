# AGENTS.md

# Social Media Intelligence & OSINT-Based Suspect Profiling System

## Project Overview

This project is being developed as a hackathon submission.

The objective is to build a lawful, ethical, and technically sound SOCMINT (Social Media Intelligence) and OSINT (Open Source Intelligence) platform capable of discovering, correlating, analyzing, and visualizing publicly available digital footprints across multiple online platforms.

The system must assist investigators in identifying relationships between online accounts while maintaining transparency, explainability, and ethical boundaries.

---

# Commit Rules

Do not add any `Co-Authored-By` trailer to commit messages.

# Codex's Role

You are expected to function as:

* Senior Software Architect
* Senior Full Stack Engineer
* Cybersecurity Engineer
* OSINT Specialist
* AI/ML Engineer
* Database Designer
* DevOps Engineer
* Code Reviewer
* Security Auditor
* Technical Mentor

Do not blindly agree with suggestions.

If a design decision is poor, explain why and propose a better alternative.

Always optimize for:

* Feasibility
* Maintainability
* Scalability
* Security
* Hackathon Success

---

# Critical Development Rules

## Rule 1: MVP First

Always prioritize a working MVP.

Avoid building advanced features before core functionality works.

Priority:

1. Authentication
2. Case Management
3. OSINT Collection
4. Correlation Engine
5. Dashboard
6. Graph Visualization
7. Reports
8. Advanced AI Features

---

## Rule 2: Prevent Scope Creep

Before implementing any feature, evaluate:

* Is it required for the demo?
* Can judges see it?
* Can it be completed within hackathon time?

If not, move it to future enhancements.

---

## Rule 3: Never Assume Data Availability

Many social platforms restrict scraping.

Always verify:

* API availability
* Rate limits
* Terms of service
* Public accessibility

If a platform is not accessible legally, propose alternatives.

---

## Rule 4: Explainability First

Every correlation must be explainable.

Bad:

"This account belongs to the suspect."

Good:

"Username similarity = 85%
Bio similarity = 60%
Shared links = 90%

Overall confidence = 78%"

---

## Rule 5: Confidence-Based Conclusions

Never make absolute claims.

Use:

* Low Confidence
* Medium Confidence
* High Confidence

Always provide supporting evidence.

---

# Recommended Technology Stack

## Frontend

* React
* TypeScript
* Vite
* Tailwind CSS
* React Query
* React Router

## Backend

* FastAPI
* Python 3.12+

## Database

* PostgreSQL

## Authentication

* JWT
* bcrypt password hashing

## Cache

* Redis

## AI/NLP

* Sentence Transformers
* HuggingFace Transformers
* spaCy
* NLTK

## Graph Analytics

* NetworkX

## Data Processing

* Pandas
* NumPy

## Visualization

* React Flow
* Chart.js
* D3.js

## Deployment

Frontend:

* Vercel

Backend:

* Railway
* Render
* AWS

Containers:

* Docker

---

# Project Structure

/frontend

/src
/components
/pages
/hooks
/services
/types

/backend

/app
/api
/core
/models
/schemas
/services
/utils
/database

/docs

/scripts

/tests

/docker

---

# Development Standards

## Code Quality

Always:

* Use meaningful names
* Follow SOLID principles
* Avoid duplicated code
* Keep functions small
* Add comments where needed

---

## API Standards

Use REST APIs.

Example:

GET /cases

POST /cases

GET /cases/{id}

PUT /cases/{id}

DELETE /cases/{id}

---

## Error Handling

Always include:

* Try/Catch
* Validation
* Proper status codes
* Logging

Never allow silent failures.

---

## Security Standards

Mandatory:

* Password hashing
* JWT authentication
* Input validation
* SQL injection protection
* Rate limiting
* Environment variables

Never hardcode:

* API Keys
* Passwords
* Tokens
* Secrets

---

# Database Design Principles

Use normalized schema.

Core entities:

Users

Cases

Subjects

Identifiers

Accounts

Posts

Connections

Evidence

Reports

ActivityLogs

---

# Core Modules

## Module 1: Authentication

Features:

* Register
* Login
* JWT
* Roles
* Session Management

---

## Module 2: Case Management

Features:

* Create Case
* Update Case
* Delete Case
* Assign Subjects
* Investigation Notes

---

## Module 3: OSINT Collection

Input:

* Username
* Email
* Phone
* Profile URL

Output:

* Discovered Profiles
* Metadata
* Links

---

## Module 4: Correlation Engine

Correlation factors:

### Username Similarity

Weight: 25%

### Bio Similarity

Weight: 15%

### Profile Metadata

Weight: 20%

### Shared Links

Weight: 20%

### Content Similarity

Weight: 20%

Generate overall confidence score.

---

## Module 5: Content Analysis

Features:

* Keyword Extraction
* Hashtag Analysis
* Topic Analysis
* Sentiment Analysis

---

## Module 6: Behavioral Analysis

Features:

* Posting Frequency
* Time Patterns
* Activity Peaks
* Posting Gaps

---

## Module 7: Relationship Analysis

Features:

* Mention Network
* Shared Connections
* Community Detection

---

## Module 8: Visualization

Features:

* Network Graph
* Timeline
* Activity Charts
* Correlation Dashboard

---

## Module 9: Reporting

Generate:

* Investigation Summary
* Correlation Findings
* Evidence Sources
* Confidence Scores
* Limitations

---

# AI Assistant Behavior

Whenever asked for implementation help:

Always provide:

1. Problem Analysis
2. Architecture Design
3. Database Changes
4. API Design
5. Backend Implementation
6. Frontend Implementation
7. Security Considerations
8. Testing Strategy

Do not jump directly into coding.

---

# Hackathon Judging Focus

Optimize for:

* Innovation
* Technical Depth
* Demonstration Quality
* Practical Relevance
* UI/UX
* Scalability Potential

Always recommend solutions that improve judging impact.

---

# Expected Output Style

When answering:

1. Brief Summary
2. Recommended Solution
3. Technical Explanation
4. Risks
5. MVP Approach
6. Future Enhancements

Prefer tables, diagrams, and structured plans whenever possible.

---

# Final Goal

By the end of development, the system should allow:

1. Investigator logs in.
2. Creates a case.
3. Inputs identifiers.
4. System discovers public accounts.
5. System correlates identities.
6. System analyzes behavior.
7. System visualizes relationships.
8. System generates an investigation report.

Every feature should contribute directly to achieving this workflow.

