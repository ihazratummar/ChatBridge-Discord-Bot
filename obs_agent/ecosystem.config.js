module.exports = {
  apps: [
    {
      name: "obs-agent-xsophiex",
      script: ".venv/bin/python",
      args: "obs_agent.py --creator xsophiex --port 8081 --obs-port 4455",
      cwd: __dirname,
      autorestart: true,
      max_restarts: 10,
      restart_delay: 2000,
      env: {
        PYTHONUNBUFFERED: "1"
      }
    },
    {
      name: "obs-agent-chantalkuyt",
      script: ".venv/bin/python",
      args: "obs_agent.py --creator chantalkuyt --port 8082 --obs-port 4456",
      cwd: __dirname,
      autorestart: true,
      max_restarts: 10,
      restart_delay: 2000,
      env: {
        PYTHONUNBUFFERED: "1"
      }
    },
    {
      name: "obs-agent-aylen",
      script: ".venv/bin/python",
      args: "obs_agent.py --creator aylen --port 8083 --obs-port 4457",
      cwd: __dirname,
      autorestart: true,
      max_restarts: 10,
      restart_delay: 2000,
      env: {
        PYTHONUNBUFFERED: "1"
      }
    },
    {
      name: "obs-agent-zoelynn",
      script: ".venv/bin/python",
      args: "obs_agent.py --creator zoelynn --port 8084 --obs-port 4458",
      cwd: __dirname,
      autorestart: true,
      max_restarts: 10,
      restart_delay: 2000,
      env: {
        PYTHONUNBUFFERED: "1"
      }
    },
    {
      name: "obs-agent-chantalkuytmistress",
      script: ".venv/bin/python",
      args: "obs_agent.py --creator chantalkuytmistress --port 8085 --obs-port 4459",
      cwd: __dirname,
      autorestart: true,
      max_restarts: 10,
      restart_delay: 2000,
      env: {
        PYTHONUNBUFFERED: "1"
      }
    }
  ]
};
