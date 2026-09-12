const fs = require('fs');
const https = require('https');
const path = require('path');

// Helper to parse .env file
function loadEnv() {
  const envPath = path.join(__dirname, '.env');
  if (!fs.existsSync(envPath)) return {};
  const content = fs.readFileSync(envPath, 'utf8');
  const env = {};
  content.split('\n').forEach(line => {
    const trimmed = line.trim();
    if (trimmed && !trimmed.startsWith('#') && trimmed.includes('=')) {
      const parts = trimmed.split('=');
      const key = parts[0].trim();
      const val = parts.slice(1).join('=').trim();
      env[key] = val;
    }
  });
  return env;
}

const env = loadEnv();
const apiKey = env.GEMINI_API_KEY || process.env.GEMINI_API_KEY;

console.log('='.repeat(60));
console.log('🟢 NODE.JS GEMINI API KEY & MODEL CHECKER');
console.log('='.repeat(60));

if (!apiKey) {
  console.error('❌ GEMINI_API_KEY not found in .env file!');
  process.exit(1);
}

console.log(`📌 Checking key: ${apiKey.substring(0, 10)}...${apiKey.slice(-4)} (Length: ${apiKey.length})`);
console.log('🔄 Requesting model list directly from Google API server...\n');

// 1. Query models list via REST API
const modelsUrl = `https://generativelanguage.googleapis.com/v1beta/models?key=${apiKey}`;

https.get(modelsUrl, (res) => {
  let data = '';
  res.on('data', chunk => data += chunk);
  res.on('end', () => {
    try {
      const json = JSON.parse(data);
      if (json.error) {
        console.error('❌ GOOGLE API ERROR:');
        console.error(`   Code: ${json.error.code}`);
        console.error(`   Message: ${json.error.message}`);
        console.error(`   Status: ${json.error.status}\n`);
        console.log('👉 Please get a fresh key from: https://aistudio.google.com/app/apikey');
        console.log('='.repeat(60));
        return;
      }

      console.log('✅ CONNECTED SUCCESSFULLY! Active Gemini Models:\n');
      if (json.models) {
        json.models.forEach(m => {
          if (m.name.includes('gemini')) {
            console.log(` • ${m.name.replace('models/', '')} (${m.displayName || ''})`);
          }
        });
      }

      console.log('\n' + '-'.repeat(60));
      console.log('🧪 Testing generation request on `gemini-2.0-flash`...\n');
      testGeneration(apiKey);

    } catch (e) {
      console.error('Failed to parse JSON response:', e);
    }
  });
}).on('error', (err) => {
  console.error('Network Error:', err.message);
});

function testGeneration(key) {
  const postData = JSON.stringify({
    contents: [{ parts: [{ text: "Hello! Respond with 'Node.js Gemini API is working!'" }] }]
  });

  const options = {
    hostname: 'generativelanguage.googleapis.com',
    port: 443,
    path: `/v1beta/models/gemini-3.6-flash:generateContent?key=${key}`,
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Content-Length': Buffer.byteLength(postData)
    }
  };

  const req = https.request(options, (res) => {
    let body = '';
    res.on('data', chunk => body += chunk);
    res.on('end', () => {
      try {
        const respJson = JSON.parse(body);
        if (respJson.candidates && respJson.candidates[0].content) {
          const text = respJson.candidates[0].content.parts[0].text;
          console.log(`🤖 Response: ${text.trim()}`);
          console.log('🎉 SUCCESS! Your API Key is active and ready to use!');
        } else {
          console.error('Generation response error:', body);
        }
      } catch (e) {
        console.error('Error parsing generation response:', e);
      }
      console.log('='.repeat(60));
    });
  });

  req.on('error', (e) => console.error('Generation request error:', e.message));
  req.write(postData);
  req.end();
}
