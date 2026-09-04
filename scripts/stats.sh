watch -n 1 '
echo "========== CPU ==========";
uptime;

echo;
echo "========== RAM ==========";
free -h;

echo;
echo "========== GPU ==========";
nvidia-smi --query-gpu=utilization.gpu,memory.used,memory.total,temperature.gpu,power.draw --format=csv,noheader,nounits;

echo;
echo "========== OLLAMA ==========";
ollama ps;

echo;
echo "========== LLAMA SERVER ==========";
systemctl is-active llama-server;

echo;
echo "========== ROUTER ==========";
systemctl is-active router;

echo;
echo "========== DOCKER ==========";
docker ps --format "table {{.Names}}\t{{.Status}}";
'
