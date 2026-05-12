// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import {Ownable} from "./Ownable.sol";
import "./Token.sol";

contract Vault is Ownable {
    Token public token;

    event Deposited(address indexed from, uint256 amount);

    constructor(Token _token) {
        owner = msg.sender;
        token = _token;
    }

    function deposit(uint256 amount) external onlyOwner {
        token.transfer(address(this), amount);
        emit Deposited(msg.sender, amount);
    }
}
