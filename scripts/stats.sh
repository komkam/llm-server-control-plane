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
echo;
echo "========== LLM GATEWAY ==========";
systemctl is-active llm-gateway;

echo;
echo "========== EMBEDDING CLASSIFIER ==========";
systemctl is-active embedding-classifier;

echo;
echo "========== DOCKER ==========";
docker ps --format "table {{.Names}}\t{{.Status}}";
'
