import "@nomicfoundation/hardhat-toolbox";
import "dotenv/config";
const key = process.env.RELAYER_PRIVATE_KEY;
export default {
  solidity: "0.8.24",
  networks: { fuji: { url: process.env.AVAX_RPC || "https://api.avax-test.network/ext/bc/C/rpc", chainId: 43113, accounts: key ? [key] : [] } },
};
