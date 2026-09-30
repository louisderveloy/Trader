<h1 align="center">
  <br>
  <img src="https://raw.githubusercontent.com/FortAwesome/Font-Awesome/6.x/svgs/solid/chart-line.svg" alt="Trader Bot" width="100">
  <br>
  Trader
  <br>
</h1>

<h4 align="center">A personal student project exploring algorithmic trading and full-stack development.</h4>

<p align="center">
  <a href="https://python.org">
    <img src="https://img.shields.io/badge/Python-3.13-blue.svg" alt="Python 3.13">
  </a>
  <a href="https://fastapi.tiangolo.com/">
    <img src="https://img.shields.io/badge/FastAPI-005571?style=flat&logo=fastapi" alt="FastAPI">
  </a>
  <a href="https://vuejs.org/">
    <img src="https://img.shields.io/badge/Vue.js-35495E?style=flat&logo=vue.js&logoColor=4FC08D" alt="Vue 3">
  </a>
  <a href="https://www.postgresql.org/">
    <img src="https://img.shields.io/badge/PostgreSQL-316192?style=flat&logo=postgresql&logoColor=white" alt="PostgreSQL">
  </a>
</p>

<p align="center">
  <a href="#about">About</a> •
  <a href="#architecture">Architecture</a> •
  <a href="#tech-stack">Tech Stack</a> •
  <a href="#learning-milestones--challenges">Learning Milestones</a> •
  <a href="#security-practices">Security Practices</a>
</p>

---

## About

**Trader** is a personal student project built for learning and experimentation. It combines a Python-based trading bot with a real-time monitoring dashboard, serving as a sandbox to explore automated trading strategies, full-stack development, and system architecture.

Built with modern async paradigms, Trader was developed to help me practice and understand how to build robust applications.

## Architecture

Trader features a decoupled architecture, which I designed to learn about system stability and component interaction.

Instead of traditional microservice architectures that rely on HTTP APIs or Redis for inter-process communication, I experimented with using **PostgreSQL LISTEN/NOTIFY**. The Python Trading Bot, the REST API, and the Vue Dashboard communicate via the database layer.

This design choice allowed me to explore:

- **Persistence:** Recording messages and state changes naturally in the database.
- **Infrastructure Simplicity:** Avoiding the need for a separate message broker like Redis or RabbitMQ during my studies.

## Tech Stack

- **Core & Bot:** [Python 3.13](https://www.python.org/)
- **API Backend:** [FastAPI](https://fastapi.tiangolo.com/)
- **Frontend Dashboard:** [Vue 3](https://vuejs.org/)
- **Database:** [PostgreSQL](https://www.postgresql.org/) & [TimescaleDB](https://www.timescale.com/) for time-series market data.
- **Backtesting & Analytics:** [VectorBT](https://vectorbt.dev/)
- **Hyperparameter Optimization:** [Optuna](https://optuna.org/)

## Trading Strategies Explored

A major focus of this project has been the iterative design and testing of algorithmic trading strategies. My journey started with traditional technical analysis and is progressively shifting toward Machine Learning.

### 1. Traditional Technical Indicators (Linear Regression)

**The Approach:** Initially, the bot's core strategy relied on a weighted average of standard technical indicators (e.g., MACD, RSI, ATR, VWAP, OBV). I used a linear regression model over historical data (15m timeframe) to determine the optimal weights for these indicators.
**The Outcome:** While this provided a solid foundation for building the backtesting engine and learning how to use VectorBT, the returns were not consistently profitable enough to beat dynamic market conditions and exchange fees.

### 2. Strict Risk Management

**The Approach:** To mitigate losses from the initial mathematical model, I implemented a strict risk management policy. I hardcoded a `max_drawdown_tolerance` threshold to force the bot to take profits early and cut losses quickly before a deep drawdown could occur.
**The Outcome:** This improved capital preservation but highlighted the limitations of static indicators in a highly volatile market like Bitcoin.

### 3. Transition to Artificial Intelligence (In Progress)

**The Future:** Recognizing the limits of classical regression, I am currently exploring Deep Learning architectures in a separate R&D repository (`Trader_Artificial_Intelligence`). Once a robust AI model (such as a hybrid CNN/GRU or XGBoost) proves capable of dynamically predicting market regimes, it will eventually replace the legacy indicator-based strategy in this main production engine.

## Security Practices

As part of my learning journey, I implemented several security best practices to understand how to protect APIs and handle user data:

- **Authentication & Authorization:** Practiced secure session management using **HttpOnly JWTs** to mitigate XSS attacks.
- **Request Integrity:** Implemented **CSRF protection** mechanisms.
- **API Protection:** Added **Rate Limiting** to understand how to mitigate brute-force attacks.
- **Database Security:** Used **parameterized SQL queries** (via async ORMs) to prevent SQL injection vulnerabilities.

---

> _This repository is maintained as a personal student project and a record of my learning journey in software engineering, async Python, and secure systems design._
