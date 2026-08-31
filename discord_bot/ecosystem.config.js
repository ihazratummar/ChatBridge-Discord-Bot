module.exports = {
  apps: [
    {
      name: "discord-bot",
      script: ".venv/bin/python",
      args: "main.py",
      cwd: __dirname,
      autorestart: true,
      watch: false,
      max_memory_restart: "500M",
      env: {
        PYTHONUNBUFFERED: "1"
      }
    }
  ]
};
