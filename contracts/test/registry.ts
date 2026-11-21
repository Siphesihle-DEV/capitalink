import { expect } from "hardhat";
import { ethers } from "hardhat";
describe("SMEFinancingRegistry", () => {
  it("records lifecycle, blocks duplicates and non-relayers", async () => {
    const [owner, other] = await ethers.getSigners();
    const c = await (await ethers.getContractFactory("SMEFinancingRegistry")).deploy(owner.address);
    const id = ethers.id("loan-1"), ref = ethers.id("pay-1");
    await c.registerFinancing(id, 150000, ethers.id("app"));
    await c.recordRepayment(id, 1000, 900, 100, ref);
    await expect(c.recordRepayment(id, 1000, 900, 100, ref)).to.be.revertedWith("duplicate ref");
    await expect(c.connect(other).recordDistribution(id, 1, ethers.id("x"))).to.be.reverted;
    expect((await c.getFinancingHistory(id)).length).to.equal(2);
  });
});
