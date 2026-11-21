import { ethers } from "hardhat";
async function main() {
  const [deployer] = await ethers.getSigners();
  const c = await (await ethers.getContractFactory("SMEFinancingRegistry")).deploy(deployer.address); // deployer is also the relayer for the demo
  await c.waitForDeployment();
  console.log("REGISTRY_ADDRESS=" + (await c.getAddress()));
}
main().catch((e) => { console.error(e); process.exit(1); });
