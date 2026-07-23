FROM node:lts-alpine

WORKDIR /app

# Install dependencies separately for better Docker caching
COPY package*.json ./
RUN npm install

COPY . .

EXPOSE 3000

CMD ["npm", "run", "dev"]


