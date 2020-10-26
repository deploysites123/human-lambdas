cat <<EOF > /etc/nginx/conf.d/proxy.conf
client_max_body_size 50M;
server_names_hash_bucket_size 512;
map $http_upgrade $connection_upgrade {
  default        "upgrade";
  ""            "";
}
server {
  listen 80;
  server_name _ default;
  return 444;
}
server {
  listen 80;
  server_name $SERVER_NAME;
  gzip on;
      gzip_comp_level 4;
      gzip_types text/plain text/css application/json application/x-javascript text/xml application/xml application/xml+rss text/javascript;
  if ($time_iso8601 ~ "^(\d{4})-(\d{2})-(\d{2})T(\d{2})") {
      set $year $1;
      set $month $2;
      set $day $3;
      set $hour $4;
  }
  access_log /var/log/nginx/healthd/application.log.$year-$month-$day-$hour healthd;
  access_log    /var/log/nginx/access.log;
  location /static/ {
      root /var/www/static;
  }
  location / {
      proxy_pass            http://docker;
      proxy_http_version    1.1;
      proxy_set_header    Connection            $connection_upgrade;
      proxy_set_header    Upgrade                $http_upgrade;
      proxy_set_header    Host                $host;
      proxy_set_header    X-Real-IP            $remote_addr;
      proxy_set_header    X-Forwarded-For        $proxy_add_x_forwarded_for;
  }
}
EOF