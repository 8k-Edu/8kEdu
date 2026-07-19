// pm2 process definitions for the 8kEdu server deploy.
//   pm2 start deploy/ecosystem.config.js && pm2 save
// Both apps auto-load /home/projects/8kEdu/.env (cwd-relative), so no env block needed.
// exp_backoff_restart_delay makes pm2 keep restarting a crash-looping process forever
// (with growing delay) instead of marking it "errored" and giving up.
const common = {
  cwd: '/home/projects/8kEdu',
  script: '.venv/bin/python',
  interpreter: 'none',
  autorestart: true,
  min_uptime: '10s',
  exp_backoff_restart_delay: 200,
  max_memory_restart: '700M',
  kill_timeout: 5000,
}

module.exports = {
  apps: [
    { ...common, name: 'kedu-serve', args: 'serve.py --backend openrouter --port 8756' },
    { ...common, name: 'kedu-api', args: '-m agent.api --port 8787' },
  ],
}
