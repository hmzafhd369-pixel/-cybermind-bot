module.exports = {
  apps : [{
    name: "almihwar-bot",
    script: "python3",
    args: "bot_main.py",
    cwd: "/home/ubuntu/almihwar_bot",
    interpreter: "none",
    autorestart: true,
    watch: false,
    max_memory_restart: '500M',
    env: {
      NODE_ENV: "production",
    }
  }]
}
