# 🏦 Bank Nifty Scalping Bot

A high-frequency scalping bot for Bank Nifty options using the [DhanHQ API](https://dhanhq.co/). Built with Python's async/await architecture for efficient, event-driven trading.

![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)
![License](https://img.shields.io/badge/License-MIT-green.svg)
![Status](https://img.shields.io/badge/Status-Development-orange.svg)

## ⚠️ Disclaimer

**This software is for educational purposes only. Trading in financial markets involves substantial risk of loss. Past performance is not indicative of future results. Use at your own risk.**

---

## 📋 Features

- **High-Frequency Scalping** - Optimized for quick entry/exit on Bank Nifty options
- **Async Event-Driven Architecture** - Efficient processing with asyncio queues
- **Dual Momentum Strategy** - Combines EMA, RSI, and MACD for signal generation
- **Real-Time Candle Building** - Constructs OHLCV candles from tick data
- **WebSocket Market Feed** - Live streaming data via DhanHQ WebSocket
- **Risk Management** - Configurable stop-loss, targets, and trailing stops
- **Paper Trading Mode** - Test strategies without risking real money
- **Rate Limit Handling** - Respects API rate limits (25 orders/second)

## 🏗️ Architecture

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│  Market Feed    │───▶│  Candle Builder │───▶│  Alpha Engine   │
│  (Producer)     │    │  (Aggregator)   │    │  (Strategy)     │
└─────────────────┘    └─────────────────┘    └─────────────────┘
                                                       │
                                                       ▼
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│  Position Mgr   │◀───│  Order Manager  │◀───│  Signal Queue   │
│  (Risk)         │    │  (Executor)     │    │  (Consumer)     │
└─────────────────┘    └─────────────────┘    └─────────────────┘
```

## 📁 Project Structure

```
dhan-trader-bot/
├── main.py           # Core orchestrator and trading engine
├── strategy.py       # Dual momentum scalping strategy
├── indicators.py     # Technical indicators (EMA, RSI, MACD, ATR)
├── candle_builder.py # Real-time OHLCV candle construction
├── order_manager.py  # Order execution and position management
├── market_feed.py    # DhanHQ WebSocket market data handler
├── config.py         # Configuration and environment settings
├── models.py         # Data models and structures
├── utils.py          # Helper utilities and logging
└── requirements.txt  # Python dependencies
```

## 🚀 Quick Start

### Prerequisites

- Python 3.10 or higher
- DhanHQ trading account with API access
- TA-Lib C library (for technical indicators)

### 1. Clone the Repository

```bash
git clone https://github.com/vishwamartur/dhan-trader-bot.git
cd dhan-trader-bot
```

### 2. Install TA-Lib C Library

**Windows:**
Download and install from [TA-Lib Windows](https://github.com/mrjbq7/ta-lib#windows)

**macOS:**
```bash
brew install ta-lib
```

**Linux (Ubuntu/Debian):**
```bash
sudo apt-get install ta-lib
# Or build from source:
wget http://prdownloads.sourceforge.net/ta-lib/ta-lib-0.4.0-src.tar.gz
tar -xzf ta-lib-0.4.0-src.tar.gz
cd ta-lib/
./configure --prefix=/usr
make
sudo make install
```

### 3. Install Python Dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure API Credentials

Set environment variables:

```bash
# Linux/macOS
export DHAN_CLIENT_ID="your_client_id"
export DHAN_ACCESS_TOKEN="your_access_token"

# Windows (PowerShell)
$env:DHAN_CLIENT_ID="your_client_id"
$env:DHAN_ACCESS_TOKEN="your_access_token"
```

Or create a `.env` file:
```
DHAN_CLIENT_ID=your_client_id
DHAN_ACCESS_TOKEN=your_access_token
```

### 5. Run the Bot

**Paper Trading Mode (Recommended for Testing):**
```bash
python main.py
```

**Live Trading Mode:**
```bash
python main.py --live
```

**Test API Connection:**
```bash
python main.py --test-connection
```

## ⚙️ Configuration

Edit `config.py` to customize:

| Parameter | Default | Description |
|-----------|---------|-------------|
| `PAPER_TRADING` | `True` | Enable/disable paper trading |
| `LOT_SIZE` | `15` | Bank Nifty lot size |
| `NUM_LOTS` | `2` | Number of lots per trade |
| `STOP_LOSS_POINTS` | `20.0` | Stop loss in points |
| `TARGET_POINTS` | `40.0` | Target profit in points |
| `MAX_DAILY_LOSS` | `5000.0` | Maximum daily loss (INR) |
| `CANDLE_TIMEFRAME_SECONDS` | `60` | Candle period (1 min) |
| `EMA_PERIOD` | `9` | EMA indicator period |
| `RSI_PERIOD` | `14` | RSI indicator period |

## 📊 Strategy Overview

The bot uses a **Dual Momentum Strategy**:

1. **EMA Crossover** - Price crossing above/below 9-period EMA
2. **RSI Filter** - RSI > 60 for longs, RSI < 40 for shorts
3. **MACD Confirmation** - MACD histogram direction alignment

### Entry Conditions

| Signal | Conditions |
|--------|------------|
| **LONG** | Price > EMA(9) + RSI > 60 + MACD histogram positive |
| **SHORT** | Price < EMA(9) + RSI < 40 + MACD histogram negative |

### Exit Conditions

- **Stop Loss** - Fixed points below entry
- **Target** - Fixed points above entry
- **Trailing Stop** - Dynamic stop adjustment as price moves favorably

## 🔒 Risk Management

- Maximum 1 position at a time
- Fixed stop-loss and target levels
- Daily loss limit enforcement
- Rate limit compliance (25 orders/second)
- Graceful shutdown with position closing

## 📝 Logging

Logs are written to `logs/trading.log` with the following format:
```
2024-01-21 09:30:15 | INFO | 📊 Tick processor started
2024-01-21 09:30:15 | INFO | 🧠 Signal processor started
2024-01-21 09:30:15 | INFO | 💰 Order executor started
```

## 🛠️ Development

### Running Tests
```bash
python -m pytest tests/
```

### Code Structure

- **Async Queues** - Tick, Candle, and Signal queues for decoupled processing
- **Event-Driven** - Callbacks for candle completion and signal generation
- **Graceful Shutdown** - Signal handlers for clean termination

## 📚 API Reference

This bot uses the official [DhanHQ Python SDK](https://github.com/dhan-oss/DhanHQ-py):

- [DhanHQ API Documentation](https://dhanhq.co/docs/v2/)
- [WebSocket Market Feed](https://dhanhq.co/docs/v2/live-market-feed/)
- [Order Placement](https://dhanhq.co/docs/v2/orders/)

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit changes (`git commit -m 'Add amazing feature'`)
4. Push to branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 📧 Contact

- GitHub: [@vishwamartur](https://github.com/vishwamartur)

---

**Made with ❤️ for algorithmic traders**
